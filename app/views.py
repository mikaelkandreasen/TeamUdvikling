"""Forside, mobilforside, menu og kriterie-side."""
import io

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, session, url_for

from . import activity, club, model, teams
from .db import get_db
from .team import team_criteria, team_focus
from .helpers import active_players, default_round, round_info, round_window, team_id

bp = Blueprint("main", __name__)


def _dashboard_data(db):
    uid = g.user["id"]
    players = active_players(db)
    rounds = model.load_rounds(db, team_id())
    mine = {r: {} for r in g.rounds}
    for row in db.execute("SELECT round, player_id, COUNT(*) n FROM evaluations WHERE trainer_id=? GROUP BY round, player_id", (uid,)):
        mine[row["round"]][row["player_id"]] = row["n"]
    prog = []
    for info in round_info(db):
        done = sum(1 for p in players if mine[info["no"]].get(p["id"]) == model.N_CRIT)
        prog.append(dict(info, done=done, total=len(players)))
    shown = round_window(prog)
    return players, rounds, [dict(r, shown=r["no"] in shown) for r in prog]


@bp.route("/")
def home():
    ua = request.headers.get("User-Agent", "")
    if "Mobi" in ua and not request.args.get("desktop"):
        return redirect(url_for("main.mobile"))
    db = get_db()
    players, rounds, prog = _dashboard_data(db)
    return render_template("home.html", players=players, prog=prog, tfocus=team_focus(db, team_id()) if g.get("team") else None)


@bp.route("/m")
def mobile():
    """Mobilforside: store trykflader, spillerliste med seneste score."""
    db = get_db()
    players, rounds, prog = _dashboard_data(db)
    cards = []
    for p in players:
        r, res = model.latest(rounds, p["id"])
        cards.append(dict(p=p, round=r, samlet=res["samlet"] if res else None))
    cur = default_round(rounds)
    return render_template("mobile_home.html", cards=cards, prog=prog, cur=cur, tfocus=team_focus(db, team_id()) if g.get("team") else None)


@bp.route("/aktivitet")
def activity_now():
    """Hvem er aktive nu: eget hold for alle; alle hold (med holdnavn) kun for administratorer."""
    from datetime import datetime
    import time
    info = activity.summary(get_db(), g.user, g.team)
    zone = activity.tz()
    now = int(time.time())

    def ago(r):
        mins = max(0, (now - r["last_seen"]) // 60)
        return "lige nu" if mins < 1 else f"for {mins} min. siden"
    return render_template("activity_now.html", info=info, ago=ago, fmt=lambda r: datetime.fromtimestamp(r["last_seen"], zone).strftime("%H:%M"))


@bp.route("/menu")
def menu():
    return render_template("menu.html")


@bp.route("/criteria")
def criteria():
    return render_template("criteria.html", criteria=team_criteria(get_db(), g.team["id"]) if g.get("team") else model.CRITERIA, role_def=model.ROLE_DEF)


@bp.route("/switch-team", methods=["POST"])
def switch_team():
    db = get_db()
    tid = request.form.get("team_id", type=int)
    if tid is None or not teams.switch(db, g.user, tid):
        abort(403)
    return redirect(url_for("main.home", desktop=1) if "Mobi" not in request.headers.get("User-Agent", "") else url_for("main.mobile"))


@bp.route("/switch-profile", methods=["POST"])
def switch_profile():
    from . import profiles
    db = get_db()
    real = g.get("real_user") or g.user
    if not profiles.switch(db, real, request.form.get("profile_id", type=int) or 0):
        abort(403)
    session.pop("team_id", None)
    return redirect(url_for("main.home"))


@bp.route("/no-team")
def no_team():
    if g.get("team"):
        return redirect(url_for("main.home"))
    return render_template("no_team.html")


@bp.route("/branding/logo/<int:cid>")
def club_logo(cid):
    """En klubs logo (offentligt, så det kan vises på loginsiden)."""
    row = get_db().execute("SELECT logo, logo_mime FROM clubs WHERE id=?", (cid,)).fetchone()
    if not row or not row["logo"]:
        abort(404)
    return send_file(io.BytesIO(row["logo"]), mimetype=row["logo_mime"])


@bp.route("/privatliv")
def privacy():
    """Offentlig privatlivsinformation (GDPR art. 13). Skabelon – tilpasses af klubben."""
    return render_template("privacy.html")
