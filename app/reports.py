"""Samlet spillerrapport (færdigheder + motivation + udvikling) – printvenlig A4."""
from flask import Blueprint, render_template, request

from . import devdata, evaluation, model, motivation
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
