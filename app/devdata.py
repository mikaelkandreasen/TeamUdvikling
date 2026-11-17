"""Udviklingsdata: relativ alder, fremmøde, trivsel, motorik og handleplan."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from . import model
from .db import audit, get_db, get_setting, set_setting
from .helpers import active_players, get_player, int_in, team_id, valid_choice

bp = Blueprint("devdata", __name__, url_prefix="/devdata")
NUM_FIELDS = [("trainings", 0, 999), ("matches", 0, 999), ("t1", 1, 5), ("t2", 1, 5), ("t3", 1, 5),
              ("m1", 1, 5), ("m2", 1, 5), ("m3", 1, 5), ("m4", 1, 5)]


def _devrow(db, pid):
    return db.execute("SELECT * FROM devdata WHERE player_id=?", (pid,)).fetchone()


def _totals(db):
    return (int_in(get_setting(db, team_id(), "trainings_total"), 1, 999), int_in(get_setting(db, team_id(), "matches_total"), 1, 999))


def player_metrics(db, p, rounds, dev, totals):
    d = model.parse_date(p["birth_date"])
    _r, res = model.latest(rounds, p["id"])
    g = (lambda k: dev[k] if dev and dev[k] is not None else None)
    return dict(
        p=p, birth=d, q=model.quarter(d) if d else None, months=model.months_after_jan1(d) if d else None,
        samlet=res["samlet"] if res else None,
        att=model.ratio(g("trainings"), totals[0]), matchp=model.ratio(g("matches"), totals[1]),
        trivsel=model.mean([g("t1"), g("t2"), g("t3")]), motorik=model.mean([g("m1"), g("m2"), g("m3"), g("m4")]), dev=dev)


def overview(db):
    rounds = model.load_rounds(db, team_id())
    totals = _totals(db)
    rows = []
    for p in active_players(db):
        rows.append(player_metrics(db, p, rounds, _devrow(db, p["id"]), totals))
    quarters = []
    for q in (1, 2, 3, 4):
        sel = [r for r in rows if r["q"] == q]
        quarters.append(dict(q=q, n=len(sel), score=model.mean([r["samlet"] for r in sel]), att=model.mean([r["att"] for r in sel]),
                             matchp=model.mean([r["matchp"] for r in sel]), trivsel=model.mean([r["trivsel"] for r in sel])))
    n_all = sum(x["n"] for x in quarters)
    for x in quarters:
        x["share"] = x["n"] / n_all if n_all else None
    first_half = (quarters[0]["n"] + quarters[1]["n"]) / n_all if n_all else None
    notes = []
    if n_all:
        if first_half >= 0.65:
            notes.append("Overvægt af tidligt fødte (mindst 65% i 1. halvår) – typisk relativ aldersskævhed. Overvej at give de yngste ekstra tid og spilletid.")
        elif first_half <= 0.35:
            notes.append("Overvægt af sent fødte – ualmindeligt; tjek fødselsdatoer.")
        else:
            notes.append("Fødselsfordelingen over året ser balanceret ud.")
    s1, s4 = quarters[0]["score"], quarters[3]["score"]
    if s1 is not None and s4 is not None and s1 - s4 >= 0.5:
        notes.append("Tidligt fødte (Q1) scorer mindst 0,5 over sent fødte (Q4). Overvej, om forskellen skyldes alder frem for talent.")
    avg = dict(att=model.mean([r["att"] for r in rows]), matchp=model.mean([r["matchp"] for r in rows]),
               trivsel=model.mean([r["trivsel"] for r in rows]), motorik=model.mean([r["motorik"] for r in rows]),
               samlet=model.mean([r["samlet"] for r in rows]),
               **{k: model.mean([(r["dev"][k] if r["dev"] and r["dev"][k] is not None else None) for r in rows]) for k in ("t1", "t2", "t3", "m1", "m2", "m3", "m4")})
    return dict(rows=rows, quarters=quarters, first_half=first_half, notes=notes, avg=avg, totals=totals)


def report_data(db, pid):
    ov = overview(db)
    p = get_player(db, pid)
    mine = next((r for r in ov["rows"] if r["p"]["id"] == pid), None)
    if mine is None:  # inaktiv spiller: beregn alligevel
        mine = player_metrics(db, p, model.load_rounds(db, team_id()), _devrow(db, pid), ov["totals"])
    return dict(m=mine, avg=ov["avg"], note=model.age_note(mine["q"]) if mine["q"] else "")


@bp.route("/", methods=["GET", "POST"])
def matrix():
    db = get_db()
    players = active_players(db)
    if request.method == "POST":
        for key in ("trainings_total", "matches_total"):
            v = int_in(request.form.get(key), 0, 999)
            set_setting(db, team_id(), key, str(v) if v else "")
        for p in players:
            db.execute("INSERT OR IGNORE INTO devdata(player_id) VALUES(?)", (p["id"],))
            for f, lo, hi in NUM_FIELDS:
                v = int_in(request.form.get(f"{f}_{p['id']}"), lo, hi)
                db.execute(f"UPDATE devdata SET {f}=? WHERE player_id=?", (v, p["id"]))
        audit(db, g.user["username"], "udviklingsdata_gemt")
        db.commit()
        flash("Udviklingsdata gemt.", "ok")
        return redirect(url_for("devdata.matrix"))
    ov = overview(db)
    return render_template("devdata.html", ov=ov, trivsel=model.TRIVSEL, motorik=model.MOTORIK,
                           trainings_total=get_setting(db, team_id(), "trainings_total"), matches_total=get_setting(db, team_id(), "matches_total"))


@bp.route("/<int:pid>", methods=["GET", "POST"])
def plan(pid):
    db = get_db()
    p = get_player(db, pid)
    if request.method == "POST":
        fu = (request.form.get("followup") or "").strip()
        if fu and not model.parse_date(fu):
            flash("Ugyldig dato.", "error")
            fu = ""
        db.execute("INSERT OR IGNORE INTO devdata(player_id) VALUES(?)", (pid,))
        db.execute("UPDATE devdata SET tiltag=?, eget_maal=?, followup=?, status=? WHERE player_id=?",
                   ((request.form.get("tiltag") or "").strip()[:1000] or None, (request.form.get("eget_maal") or "").strip()[:1000] or None,
                    fu or None, valid_choice(request.form.get("status"), model.STATUSES), pid))
        db.commit()
        flash("Handleplan gemt.", "ok")
        return redirect(url_for("devdata.plan", pid=pid))
    return render_template("devdata_plan.html", p=p, d=_devrow(db, pid))
