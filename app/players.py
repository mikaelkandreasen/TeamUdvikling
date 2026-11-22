"""Spillerliste (tom ved start) – oprettelse, redigering, sletning (admin) og dataudtræk pr. spiller."""
import base64
import json

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from . import model, photos, transfer
from .auth import admin_required
from .db import audit, get_db
from .helpers import get_player, photo_ids, team_id, valid_choice

bp = Blueprint("players", __name__, url_prefix="/players")
FIELDS = ["name", "birth_date", "shirt_no", *model.POSITION_FIELDS, "level", "foot", "start_date", "focus1", "focus2", "notes"]


def _read_form():
    f = {k: (request.form.get(k, "") or "").strip() for k in FIELDS}
    errors = []
    if not f["name"]:
        errors.append("Navn mangler.")
    for k in ("birth_date", "start_date"):
        if f[k] and not model.parse_date(f[k]):
            errors.append("Ugyldig dato (brug ÅÅÅÅ-MM-DD).")
            f[k] = ""
    chosen = []                                   # op til 4 positionsvalg: ugyldige og dubletter fjernes, valgene rykkes sammen
    for k in model.POSITION_FIELDS:
        v = valid_choice(f[k], model.POSITIONS)
        if v and v not in chosen:
            chosen.append(v)
    for i, k in enumerate(model.POSITION_FIELDS):
        f[k] = chosen[i] if i < len(chosen) else ""
    f["foot"] = valid_choice(f["foot"], model.FEET) or ""
    f["level"] = valid_choice(f["level"], model.LEVELS) or ""
    f["active"] = 1 if request.form.get("active") else 0
    return f, errors


@bp.route("/")
def index():
    db = get_db()
    show_all = request.args.get("alle") == "1"
    sql = "SELECT * FROM players WHERE team_id=?" + ("" if show_all else " AND active=1") + " ORDER BY name COLLATE NOCASE"
    rows = db.execute(sql, (team_id(),)).fetchall()
    ages = {r["id"]: (model.quarter(model.parse_date(r["birth_date"])) if model.parse_date(r["birth_date"]) else None) for r in rows}
    return render_template("players_list.html", players=rows, ages=ages, show_all=show_all, photos=photo_ids(db))


@bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        f, errors = _read_form()
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("player_form.html", p=f, new=True)
        db = get_db()
        cur = db.execute(f"INSERT INTO players({','.join(FIELDS)},active,team_id) VALUES({','.join('?' * (len(FIELDS) + 2))})",
                         [f[k] or None for k in FIELDS] + [f["active"], team_id()])
        _stamp_deactivation(db, cur.lastrowid)
        audit(db, g.user["username"], "spiller_oprettet", str(cur.lastrowid))
        db.commit()
        flash("Spilleren er oprettet.", "ok")
        return redirect(url_for("players.index"))
    return render_template("player_form.html", p={"active": 1}, new=True)


def _stamp_deactivation(db, pid):
    """Opbevaringsfristen regnes fra den dag, spilleren blev inaktiv."""
    db.execute("UPDATE players SET deactivated_at=CASE WHEN active=0 THEN COALESCE(deactivated_at, date('now','localtime')) ELSE NULL END WHERE id=?", (pid,))


@bp.route("/<int:pid>/edit", methods=["GET", "POST"])
def edit(pid):
    db = get_db()
    p = get_player(db, pid)
    if request.method == "POST":
        f, errors = _read_form()
        if errors:
            for e in errors:
                flash(e, "error")
            f["id"] = pid
            return render_template("player_form.html", p=f, new=False, photo=_photo_info(db, pid), move_targets=_move_targets())
        db.execute(f"UPDATE players SET {','.join(k + '=?' for k in FIELDS)},active=? WHERE id=? AND team_id=?",
                   [f[k] or None for k in FIELDS] + [f["active"], pid, team_id()])
        _stamp_deactivation(db, pid)
        audit(db, g.user["username"], "spiller_rettet", str(pid))
        db.commit()
        flash("Gemt.", "ok")
        return redirect(url_for("players.index"))
    return render_template("player_form.html", p=dict(p), new=False, photo=_photo_info(db, pid), move_targets=_move_targets())


def _photo_info(db, pid):
    return db.execute("SELECT consent_at, updated_at FROM player_photos WHERE player_id=?", (pid,)).fetchone()


@bp.route("/<int:pid>/photo.jpg")
def photo_view(pid):
    """Billedet (hold-afgrænset: andre holds spillere giver 404). ?s=full giver det store billede, ellers miniaturen."""
    db = get_db()
    col = "full" if request.args.get("s") == "full" else "thumb"
    row = db.execute(f"SELECT pp.{col} AS img FROM player_photos pp JOIN players p ON p.id=pp.player_id WHERE pp.player_id=? AND p.team_id=?",
                     (pid, team_id())).fetchone()
    if not row:
        abort(404)
    return Response(row["img"], mimetype="image/jpeg")


@bp.route("/<int:pid>/photo", methods=["POST"])
def photo_upload(pid):
    db = get_db()
    get_player(db, pid)
    back = redirect(url_for("players.edit", pid=pid))
    if request.form.get("consent") != "ja":
        flash("Bekræft, at forældrene har givet samtykke til billedet.", "error")
        return back
    f = request.files.get("photo")
    try:
        full, thumb = photos.process(f.read(photos.MAX_UPLOAD + 1) if f else b"")
    except photos.PhotoError as e:
        flash(str(e), "error")
        return back
    db.execute("INSERT INTO player_photos(player_id,full,thumb,consent_at,updated_at) VALUES(?,?,?,datetime('now'),datetime('now')) "
               "ON CONFLICT(player_id) DO UPDATE SET full=excluded.full, thumb=excluded.thumb, consent_at=excluded.consent_at, updated_at=excluded.updated_at",
               (pid, full, thumb))
    audit(db, g.user["username"], "foto_gemt", f"id={pid}")
    db.commit()
    flash("Billedet er gemt.", "ok")
    return back


@bp.route("/<int:pid>/photo/delete", methods=["POST"])
def photo_delete(pid):
    db = get_db()
    get_player(db, pid)
    db.execute("DELETE FROM player_photos WHERE player_id=?", (pid,))
    audit(db, g.user["username"], "foto_slettet", f"id={pid}")
    db.commit()
    flash("Billedet er slettet.", "ok")
    return redirect(url_for("players.edit", pid=pid))


def _move_targets():
    """Hold spilleren kan flyttes til: andre aktive hold i samme klub, som brugeren har adgang til (kun administratorer)."""
    if g.user["role"] not in ("admin", "clubadmin") or g.get("viewing"):
        return []
    return [t for t in g.teams if t["id"] != g.team["id"] and not t["archived"] and t["club_id"] == g.team["club_id"]]


@bp.route("/<int:pid>/move", methods=["POST"])
@admin_required
def move(pid):
    db = get_db()
    p = get_player(db, pid)
    to = next((t for t in _move_targets() if t["id"] == request.form.get("team", type=int)), None)
    if not to or request.form.get("confirm") != "ja":
        flash("Vælg et hold og bekræft flytningen.", "error")
        return redirect(url_for("players.edit", pid=pid))
    transfer.move_player(db, p, to, g.user["username"])
    db.commit()
    flash(f"{p['name']} er flyttet til {to['name']}. Evalueringerne følger med som historik i profilen.", "ok")
    return redirect(url_for("players.index"))


@bp.route("/<int:pid>/delete", methods=["POST"])
@admin_required
def delete(pid):
    db = get_db()
    p = get_player(db, pid)
    if request.form.get("confirm") != "ja":
        flash("Sletning kræver bekræftelse.", "error")
        return redirect(url_for("players.edit", pid=pid))
    db.execute("DELETE FROM players WHERE id=? AND team_id=?", (pid, team_id()))
    audit(db, g.user["username"], "spiller_slettet", f"id={pid}")
    db.commit()
    flash(f"{p['name']} og alle tilhørende data er slettet.", "ok")
    return redirect(url_for("players.index"))


@bp.route("/<int:pid>/export.json")
@admin_required
def export_json(pid):
    """Indsigtsret (GDPR): alle data om én spiller som JSON."""
    db = get_db()
    p = get_player(db, pid)
    out = dict(spiller=dict(p))
    out["evalueringer"] = [dict(r) for r in db.execute(
        "SELECT round AS runde, trainer_id AS træner, crit AS kriterie, score FROM evaluations WHERE player_id=?", (pid,))]
    out["niveauvurderinger"] = [dict(r) for r in db.execute("SELECT round AS runde, trainer_id AS træner, level AS niveau FROM level_ratings WHERE player_id=?", (pid,))]
    out["niveau_udsagn"] = [dict(r) for r in db.execute("SELECT round AS runde, trainer_id AS træner, item AS udsagn FROM dbu_checks WHERE player_id=?", (pid,))]
    out["motivation"] = [dict(r) for r in db.execute("SELECT qidx AS spørgsmål, score FROM motivation_answers WHERE player_id=?", (pid,))]
    out["motivation_over_tid"] = [dict(r) for r in db.execute("SELECT qidx AS spørgsmål, score, taken_on AS dato FROM motivation_log WHERE player_id=? ORDER BY taken_on", (pid,))]
    out["spilletid"] = [dict(r) for r in db.execute("SELECT m.day AS dato, m.opponent AS modstander, s.period AS periode, s.slot AS plads, m.period_min AS minutter FROM match_slots s JOIN matches m ON m.id=s.match_id WHERE s.player_id=? ORDER BY m.day", (pid,))]
    out["samtaler"] = [dict(r) for r in db.execute("SELECT held_on AS dato, notes AS noter, agreements AS aftaler, homework AS hjemmeøvelse, trainer_name AS træner FROM conversations WHERE player_id=?", (pid,))]
    d = db.execute("SELECT * FROM devdata WHERE player_id=?", (pid,)).fetchone()
    out["udviklingsdata"] = dict(d) if d else {}
    ph = db.execute("SELECT full, consent_at FROM player_photos WHERE player_id=?", (pid,)).fetchone()
    out["foto"] = {"samtykke": ph["consent_at"], "jpeg_base64": base64.b64encode(ph["full"]).decode()} if ph else None
    out["holdopstillinger"] = [dict(r) for r in db.execute(
        "SELECT l.name AS opstilling, l.game_type AS kamptype, s.slot AS plads FROM lineup_slots s JOIN lineups l ON l.id=s.lineup_id "
        "WHERE s.player_id=? AND l.team_id=?", (pid, team_id()))]
    audit(db, g.user["username"], "spiller_eksport", f"id={pid}")
    db.commit()
    return Response(json.dumps(out, ensure_ascii=False, indent=2), mimetype="application/json",
                    headers={"Content-Disposition": f"attachment; filename=spiller-{pid}.json"})
