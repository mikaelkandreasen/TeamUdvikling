"""Spillerliste (tom ved start) – oprettelse, redigering, sletning (admin) og dataudtræk pr. spiller."""
import json

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from . import model
from .auth import admin_required
from .db import audit, get_db
from .helpers import get_player, team_id, valid_choice

bp = Blueprint("players", __name__, url_prefix="/players")
FIELDS = ["name", "birth_date", "shirt_no", "position", "position2", "foot", "start_date", "focus1", "focus2", "notes"]


def _read_form():
    f = {k: (request.form.get(k, "") or "").strip() for k in FIELDS}
    errors = []
    if not f["name"]:
        errors.append("Navn mangler.")
    for k in ("birth_date", "start_date"):
        if f[k] and not model.parse_date(f[k]):
            errors.append("Ugyldig dato (brug ÅÅÅÅ-MM-DD).")
            f[k] = ""
    f["position"] = valid_choice(f["position"], model.POSITIONS) or ""
    f["position2"] = valid_choice(f["position2"], model.POSITIONS) or ""
    f["foot"] = valid_choice(f["foot"], model.FEET) or ""
    f["active"] = 1 if request.form.get("active") else 0
    return f, errors


@bp.route("/")
def index():
    db = get_db()
    show_all = request.args.get("alle") == "1"
    sql = "SELECT * FROM players WHERE team_id=?" + ("" if show_all else " AND active=1") + " ORDER BY name COLLATE NOCASE"
    rows = db.execute(sql, (team_id(),)).fetchall()
    ages = {r["id"]: (model.quarter(model.parse_date(r["birth_date"])) if model.parse_date(r["birth_date"]) else None) for r in rows}
    return render_template("players_list.html", players=rows, ages=ages, show_all=show_all)


@bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        f, errors = _read_form()
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("player_form.html", p=f, new=True)
        db = get_db()
        cur = db.execute("INSERT INTO players(name,birth_date,shirt_no,position,position2,foot,start_date,focus1,focus2,notes,active,team_id)"
                         " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", [f[k] or None for k in FIELDS] + [f["active"], team_id()])
        audit(db, g.user["username"], "spiller_oprettet", str(cur.lastrowid))
        db.commit()
        flash("Spilleren er oprettet.", "ok")
        return redirect(url_for("players.index"))
    return render_template("player_form.html", p={"active": 1}, new=True)


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
            return render_template("player_form.html", p=f, new=False)
        db.execute("UPDATE players SET name=?,birth_date=?,shirt_no=?,position=?,position2=?,foot=?,start_date=?,"
                   "focus1=?,focus2=?,notes=?,active=? WHERE id=? AND team_id=?", [f[k] or None for k in FIELDS] + [f["active"], pid, team_id()])
        audit(db, g.user["username"], "spiller_rettet", str(pid))
        db.commit()
        flash("Gemt.", "ok")
        return redirect(url_for("players.index"))
    return render_template("player_form.html", p=dict(p), new=False)


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
    out["motivation"] = [dict(r) for r in db.execute("SELECT qidx AS spørgsmål, score FROM motivation_answers WHERE player_id=?", (pid,))]
    d = db.execute("SELECT * FROM devdata WHERE player_id=?", (pid,)).fetchone()
    out["udviklingsdata"] = dict(d) if d else {}
    audit(db, g.user["username"], "spiller_eksport", f"id={pid}")
    db.commit()
    return Response(json.dumps(out, ensure_ascii=False, indent=2), mimetype="application/json",
                    headers={"Content-Disposition": f"attachment; filename=spiller-{pid}.json"})
