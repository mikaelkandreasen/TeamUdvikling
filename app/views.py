"""Forside, mobilforside, menu og kriterie-side."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from . import activity, club, model, teams
from .db import get_db
from .helpers import active_players, default_round, round_info, team_id

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
    return players, rounds, prog


@bp.route("/")
def home():
    ua = request.headers.get("User-Agent", "")
    if "Mobi" in ua and not request.args.get("desktop"):
        return redirect(url_for("main.mobile"))
    db = get_db()
    players, rounds, prog = _dashboard_data(db)
    return render_template("home.html", players=players, prog=prog, online=activity.summary(db, g.user, g.team))


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
    return render_template("mobile_home.html", cards=cards, prog=prog, cur=cur, online=activity.summary(db, g.user, g.team))


@bp.route("/menu")
def menu():
    return render_template("menu.html")


@bp.route("/criteria")
def criteria():
    return render_template("criteria.html", criteria=model.CRITERIA, role_def=model.ROLE_DEF)


@bp.route("/switch-team", methods=["POST"])
def switch_team():
    db = get_db()
    tid = request.form.get("team_id", type=int)
    if tid is None or not teams.switch(db, g.user, tid):
        abort(403)
    return redirect(url_for("main.home", desktop=1) if "Mobi" not in request.headers.get("User-Agent", "") else url_for("main.mobile"))


@bp.route("/no-team")
def no_team():
    if g.get("team"):
        return redirect(url_for("main.home"))
    return render_template("no_team.html")


@bp.route("/branding/logo")
def club_logo():
    """Klubbens logo (offentligt, så det kan vises på loginsiden)."""
    c = club.info()
    if not c["has_logo"]:
        abort(404)
    return send_file(club.logo_path(), mimetype=club.club_get(get_db())["logo_mime"], conditional=True)


@bp.route("/privatliv")
def privacy():
    """Offentlig privatlivsinformation (GDPR art. 13). Skabelon – tilpasses af klubben."""
    return render_template("privacy.html")
