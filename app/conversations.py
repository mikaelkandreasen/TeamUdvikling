"""Forældresamtaler: dato, noter, aftaler og hjemmeøvelser pr. spiller (kun for holdets trænere)."""
import datetime

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from . import model
from .db import audit, get_db
from .helpers import get_player
from .team import can_configure

bp = Blueprint("conv", __name__, url_prefix="/samtaler")


def latest(db, pid):
    return db.execute("SELECT * FROM conversations WHERE player_id=? ORDER BY held_on DESC, id DESC LIMIT 1", (pid,)).fetchone()


def _writable():
    if g.user["readonly"] or g.team["archived"]:
        abort(403)


@bp.route("/<int:pid>")
def index(pid):
    db = get_db()
    p = get_player(db, pid)
    rows = db.execute("SELECT * FROM conversations WHERE player_id=? ORDER BY held_on DESC, id DESC", (pid,)).fetchall()
    return render_template("conversations.html", p=p, rows=rows, today=datetime.date.today().isoformat())


@bp.route("/<int:pid>/ny", methods=["POST"])
def add(pid):
    _writable()
    db = get_db()
    p = get_player(db, pid)
    day = (request.form.get("held_on") or "").strip()
    f = {k: (request.form.get(k) or "").strip()[:1500] for k in ("notes", "agreements", "homework")}
    if not model.parse_date(day) or not any(f.values()):
        flash("Angiv en dato og skriv mindst ét felt.", "error")
        return redirect(url_for("conv.index", pid=pid))
    db.execute("INSERT INTO conversations(player_id,held_on,notes,agreements,homework,trainer_id,trainer_name) VALUES(?,?,?,?,?,?,?)",
               (pid, day, f["notes"], f["agreements"], f["homework"], g.real_user["id"], g.user["display_name"]))
    audit(db, g.user["username"], "samtale_oprettet", f"spiller id={pid}")
    db.commit()
    flash("Samtalen er gemt.", "ok")
    return redirect(url_for("conv.index", pid=pid))


@bp.route("/<int:pid>/<int:cid>/slet", methods=["POST"])
def delete(pid, cid):
    _writable()
    db = get_db()
    get_player(db, pid)
    c = db.execute("SELECT * FROM conversations WHERE id=? AND player_id=?", (cid, pid)).fetchone()
    if not c:
        abort(404)
    if c["trainer_id"] != g.real_user["id"] and not can_configure():
        abort(403)
    db.execute("DELETE FROM conversations WHERE id=?", (cid,))
    audit(db, g.user["username"], "samtale_slettet", f"spiller id={pid}")
    db.commit()
    return redirect(url_for("conv.index", pid=pid))
