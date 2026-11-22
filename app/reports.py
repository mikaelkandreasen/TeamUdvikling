"""Samlet spillerrapport (færdigheder + motivation + udvikling) – printvenlig A4."""
from flask import Blueprint, render_template, request

from . import devdata, evaluation, model, motivation
from .conversations import latest as latest_conv
from .team import team_focus
from .db import get_db
from .helpers import active_players, get_player, team_id

bp = Blueprint("reports", __name__)


def _bundle(db, p, rounds, ids, rnd=None):
    return dict(p=p, prof=evaluation.profile_data(db, p, rounds, rnd), mot=motivation.report_data(db, p["id"], ids),
                dev=devdata.report_data(db, p["id"]))


@bp.route("/report/<int:pid>")
def report(pid):
    db = get_db()
    p = get_player(db, pid)
    rounds = model.load_rounds(db, team_id())
    ids = [x["id"] for x in active_players(db)]
    return render_template("report.html", bundles=[_bundle(db, p, rounds, ids, request.args.get("runde", type=int))])


def _parent_data(db, p, rounds, ids):
    """Tal-fri sammenfatning til forældre: styrker, hvad vi træner på, fremgang og spillerens egne interesser. Ingen scores, niveauer eller sammenligning."""
    prof = evaluation.profile_data(db, p, rounds, None)
    res = prof["res"]
    name = lambda c: f"{c['skill']} som {c['role'].lower()}"
    strengths = [name(c) for c, _ in prof["strongest"]] if res else []
    tf = team_focus(db, team_id())["items"]
    focus = [f for f in (p["focus1"], p["focus2"]) if f] or ([name(c) for c, _ in prof["weakest"][:2] if c] if res else [])
    progress = [name(c) for c, _ in prof["changes"]["up"]] if prof["changes"] else []
    interests = [dict(title=c["title"], top=c["top"]) for c in motivation.report_data(db, p["id"], ids) if c["top"]]
    conv = latest_conv(db, p["id"])
    label = next((i["label"] for i in prof["infos"] if i["no"] == prof["rnd"]), "")
    return dict(p=p, has=bool(res), strengths=strengths, focus=focus, team_focus=tf, homework=(conv["homework"] if conv else ""), progress=progress, interests=interests, label=label)


@bp.route("/report/<int:pid>/foraeldre")
def parent_report(pid):
    db = get_db()
    p = get_player(db, pid)
    rounds = model.load_rounds(db, team_id())
    ids = [x["id"] for x in active_players(db)]
    has_img = bool(db.execute("SELECT 1 FROM team_mascot_img WHERE team_id=?", (team_id(),)).fetchone())
    return render_template("report_parent.html", bundles=[_parent_data(db, p, rounds, ids)], has_mascot_img=has_img)


@bp.route("/reports/foraeldre")
def parent_all():
    db = get_db()
    rounds = model.load_rounds(db, team_id())
    players = active_players(db)
    ids = [x["id"] for x in players]
    has_img = bool(db.execute("SELECT 1 FROM team_mascot_img WHERE team_id=?", (team_id(),)).fetchone())
    return render_template("report_parent.html", bundles=[_parent_data(db, p, rounds, ids) for p in players], has_mascot_img=has_img)


@bp.route("/reports/all")
def report_all():
    db = get_db()
    rounds = model.load_rounds(db, team_id())
    players = active_players(db)
    ids = [x["id"] for x in players]
    return render_template("report.html", bundles=[_bundle(db, p, rounds, ids) for p in players])


@bp.route("/reports")
def index():
    return render_template("reports_index.html", players=active_players(get_db()))
