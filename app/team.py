"""Holdets side: indstillinger (chef-træner), noter, spillerniveau, slogan og mascot med rapport."""
import datetime

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from . import features, formations, model, scope
from .db import audit, get_db, get_setting, set_setting
from .helpers import active_players, int_in, team_id

bp = Blueprint("team", __name__, url_prefix="/team")


def can_configure():
    """Chef-træner for det aktive hold, klubadministrator for holdets klub eller systemadministrator."""
    if not g.get("team") or not g.get("user") or g.get("viewing"):
        return False
    return scope.can_manage_club(g.user, g.team["club_id"]) or g.team["id"] in scope.head_team_ids(get_db(), g.user)


def _need_config():
    if not can_configure():
        abort(403)


@bp.app_context_processor
def _ctx():
    return dict(can_configure=can_configure)


def profile(db, tid):
    """Holdprofil: spillere på banen (kamptype) og antal udskiftere."""
    gt = get_setting(db, tid, "game_type")
    gt = gt if gt in formations.GAME_TYPES else formations.DEFAULT_TYPE
    subs = int_in(get_setting(db, tid, "subs"), 0, 10)
    return dict(game_type=gt, size=formations.GAME_TYPES[gt], subs=2 if subs is None else subs)


@bp.route("/")
def index():
    return render_template("team_index.html", prof=profile(get_db(), team_id()), n_players=len(active_players(get_db())))


@bp.route("/settings", methods=["GET", "POST"])
def settings():
    _need_config()
    db = get_db()
    tid = team_id()
    if request.method == "POST":
        gt = request.form.get("game_type")
        subs = int_in(request.form.get("subs"), 0, 10)
        if gt not in formations.GAME_TYPES or subs is None:
            flash("Vælg kamptype og antal udskiftere (0–10).", "error")
            return redirect(url_for("team.settings"))
        set_setting(db, tid, "game_type", gt)
        set_setting(db, tid, "subs", str(subs))
        for k in features.KEYS:
            set_setting(db, tid, f"feat_{k}", "1" if request.form.get(f"feat_{k}") else "0")
        db.execute("UPDATE teams SET slogan=?, mascot_name=? WHERE id=?",
                   ((request.form.get("slogan") or "").strip()[:80] or None, (request.form.get("mascot_name") or "").strip()[:40] or None, tid))
        audit(db, g.user["username"], "holdindstillinger_gemt", g.team["name"])
        db.commit()
        flash("Holdindstillinger gemt.", "ok")
        return redirect(url_for("team.settings"))
    heads = [r["display_name"] for r in db.execute("SELECT u.display_name FROM team_heads h JOIN users u ON u.id=h.user_id WHERE h.team_id=? ORDER BY u.display_name COLLATE NOCASE", (tid,))]
    return render_template("team_settings.html", prof=profile(db, tid), feats=features.load(db, tid), FEATURES=features.FEATURES, types=formations.GAME_TYPES,
                           heads=heads, n_rounds=len(g.rounds))


# ----------------------------------------------------------------------------- noter
@bp.route("/notes")
def notes():
    db = get_db()
    rows = db.execute("SELECT * FROM team_notes WHERE team_id=? ORDER BY created_at DESC, id DESC LIMIT 200", (team_id(),)).fetchall()
    return render_template("team_notes.html", rows=rows)


@bp.route("/notes/add", methods=["POST"])
def notes_add():
    db = get_db()
    body = (request.form.get("body") or "").strip()[:2000]
    if not body:
        flash("Skriv en note.", "error")
    else:
        db.execute("INSERT INTO team_notes(team_id,user_id,author,created_at,body) VALUES(?,?,?,datetime('now','localtime'),?)",
                   (team_id(), g.user["id"], g.user["display_name"], body))
        db.commit()
        flash("Noten er gemt.", "ok")
    return redirect(url_for("team.notes"))


@bp.route("/notes/<int:nid>/delete", methods=["POST"])
def notes_delete(nid):
    db = get_db()
    n = db.execute("SELECT * FROM team_notes WHERE id=? AND team_id=?", (nid, team_id())).fetchone()
    if not n:
        abort(404)
    if n["user_id"] != g.user["id"] and not can_configure():
        abort(403)
    db.execute("DELETE FROM team_notes WHERE id=?", (nid,))
    db.commit()
    flash("Noten er slettet.", "ok")
    return redirect(url_for("team.notes"))


# ----------------------------------------------------------------------------- spillerniveau
@bp.route("/levels", methods=["GET", "POST"])
def levels():
    db = get_db()
    players = active_players(db)
    if request.method == "POST":
        n = 0
        for p in players:
            v = request.form.get(f"level_{p['id']}", "")
            v = v if v in model.LEVELS else None
            if v != p["level"]:
                db.execute("UPDATE players SET level=? WHERE id=? AND team_id=?", (v, p["id"], team_id()))
                n += 1
        if n:
            audit(db, g.user["username"], "niveau_gemt", f"{g.team['name']}: {n} spillere")
        db.commit()
        flash("Niveauerne er gemt.", "ok")
        return redirect(url_for("team.levels"))
    counts = {lv: sum(1 for p in players if p["level"] == lv) for lv in model.LEVELS}
    counts["uden"] = sum(1 for p in players if not p["level"])
    return render_template("team_levels.html", players=players, LEVELS=model.LEVELS, counts=counts)


# ----------------------------------------------------------------------------- mascot
def _today():
    return datetime.date.today().isoformat()


@bp.route("/mascot", methods=["GET", "POST"])
def mascot():
    db = get_db()
    tid = team_id()
    players = active_players(db)
    if request.method == "POST":
        pid = int_in(request.form.get("player"), 1, 10 ** 9)
        reason = request.form.get("reason")
        day = (request.form.get("taken_on") or _today()).strip()
        if pid not in {p["id"] for p in players} or reason not in model.MASCOT_REASONS or not model.parse_date(day):
            flash("Vælg spiller, årsag og en gyldig dato.", "error")
        else:
            db.execute("UPDATE mascot_log SET returned_on=? WHERE team_id=? AND returned_on IS NULL", (day, tid))      # mascotten kan kun være ét sted
            db.execute("INSERT INTO mascot_log(team_id,player_id,taken_on,reason,note,created_by) VALUES(?,?,?,?,?,?)",
                       (tid, pid, day, reason, (request.form.get("note") or "").strip()[:300] or None, g.user["display_name"]))
            audit(db, g.user["username"], "mascot_registreret", g.team["name"])
            db.commit()
            flash("Registreret.", "ok")
        return redirect(url_for("team.mascot"))
    rows = db.execute("SELECT m.*, p.name FROM mascot_log m JOIN players p ON p.id=m.player_id WHERE m.team_id=? ORDER BY m.taken_on DESC, m.id DESC LIMIT 200", (tid,)).fetchall()
    now_with = next((r for r in rows if not r["returned_on"]), None)
    return render_template("team_mascot.html", rows=rows, players=players, reasons=model.MASCOT_REASONS, today=_today(), now_with=now_with)


def _own_entry(db, mid):
    row = db.execute("SELECT * FROM mascot_log WHERE id=? AND team_id=?", (mid, team_id())).fetchone()
    if not row:
        abort(404)
    return row


@bp.route("/mascot/<int:mid>/return", methods=["POST"])
def mascot_return(mid):
    db = get_db()
    _own_entry(db, mid)
    db.execute("UPDATE mascot_log SET returned_on=? WHERE id=? AND returned_on IS NULL", (_today(), mid))
    db.commit()
    flash("Mascotten er hjemme igen.", "ok")
    return redirect(url_for("team.mascot"))


@bp.route("/mascot/<int:mid>/delete", methods=["POST"])
def mascot_delete(mid):
    db = get_db()
    _own_entry(db, mid)
    db.execute("DELETE FROM mascot_log WHERE id=?", (mid,))
    db.commit()
    flash("Registreringen er slettet.", "ok")
    return redirect(url_for("team.mascot"))


@bp.route("/mascot/report")
def mascot_report():
    db = get_db()
    tid = team_id()
    since = request.args.get("fra", "").strip()
    since = since if model.parse_date(since) else ""
    sql = "SELECT m.*, p.name FROM mascot_log m JOIN players p ON p.id=m.player_id WHERE m.team_id=?"
    args = [tid]
    if since:
        sql += " AND m.taken_on >= ?"
        args.append(since)
    log = db.execute(sql + " ORDER BY m.taken_on, m.id", args).fetchall()
    per = {}
    for r in log:
        e = per.setdefault(r["player_id"], dict(name=r["name"], n=0, last=None, reasons={}))
        e["n"] += 1
        e["last"] = max(e["last"] or "", r["taken_on"])
        e["reasons"][r["reason"]] = e["reasons"].get(r["reason"], 0) + 1
    rows = sorted(per.values(), key=lambda e: (-e["n"], e["name"].lower()))
    totals = {}
    for r in log:
        totals[r["reason"]] = totals.get(r["reason"], 0) + 1
    never = [p["name"] for p in active_players(db) if p["id"] not in per]
    return render_template("team_mascot_report.html", rows=rows, totals=totals, never=never, since=since, total=len(log), reasons=model.MASCOT_REASONS, log=log)
