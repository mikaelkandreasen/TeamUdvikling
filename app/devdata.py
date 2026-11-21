"""Udviklingsdata: relativ alder, fremmøde, trivsel, motorik og handleplan."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from . import charts, model
from .db import audit, get_db, get_setting, set_setting
from .helpers import active_players, get_player, int_in, team_id, valid_choice

bp = Blueprint("devdata", __name__, url_prefix="/devdata")
NUM_FIELDS = [("trainings", 0, 999), ("matches", 0, 999), ("t1", 1, 5), ("t2", 1, 5), ("t3", 1, 5),
              ("m1", 1, 5), ("m2", 1, 5), ("m3", 1, 5), ("m4", 1, 5)]


def _devrow(db, pid):
    return db.execute("SELECT * FROM devdata WHERE player_id=?", (pid,)).fetchone()


def _totals(db):
    return (int_in(get_setting(db, team_id(), "trainings_total"), 1, 999), int_in(get_setting(db, team_id(), "matches_total"), 1, 999))


def att_counts(db):
    """Fremmøde registreret pr. træning/kamp: ({pid: (træninger, kampe)}, (antal træninger, antal kampe)). None hvis ingen er registreret."""
    tid = team_id()
    tot = {r["kind"]: r["n"] for r in db.execute("SELECT kind, COUNT(*) n FROM att_events WHERE team_id=? GROUP BY kind", (tid,))}
    if not tot:
        return None
    per = {}
    for r in db.execute("SELECT m.player_id, e.kind, COUNT(*) n FROM att_marks m JOIN att_events e ON e.id=m.event_id WHERE e.team_id=? GROUP BY m.player_id, e.kind", (tid,)):
        per.setdefault(r["player_id"], {})[r["kind"]] = r["n"]
    return per, (tot.get("training", 0) or None, tot.get("match", 0) or None)


class _Dev(dict):
    """Som en række fra devdata, men manglende felter er None (spilleren har måske ingen række endnu)."""
    def __missing__(self, key):
        return None


def latest_wellbeing(db):
    """Seneste trivselsmåling pr. spiller i holdet: {pid: (dag, t1, t2, t3)}."""
    out = {}
    for r in db.execute("SELECT w.* FROM wellbeing w JOIN players p ON p.id=w.player_id WHERE p.team_id=? ORDER BY w.day", (team_id(),)):
        out[r["player_id"]] = r
    return out


def _dev_with_att(dev, pid, counts, wb=None):
    w = (wb or {}).get(pid)
    if not counts and not w:
        return dev
    out = _Dev(dict(dev) if dev else {})
    if w:                                           # nyeste måling afløser den enkelte værdi
        for k in ("t1", "t2", "t3"):
            out[k] = w[k]
    if not counts:
        return out
    mine = counts[0].get(pid, {})
    out["trainings"] = mine.get("training", 0) if counts[1][0] else out.get("trainings")
    out["matches"] = mine.get("match", 0) if counts[1][1] else out.get("matches")
    return out


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
    counts = att_counts(db)
    wb = latest_wellbeing(db)
    totals = counts[1] if counts else _totals(db)
    rows = []
    for p in active_players(db):
        rows.append(player_metrics(db, p, rounds, _dev_with_att(_devrow(db, p["id"]), p["id"], counts, wb), totals))
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
    return dict(rows=rows, quarters=quarters, first_half=first_half, notes=notes, avg=avg, totals=totals, auto=counts is not None)


def report_data(db, pid):
    ov = overview(db)
    p = get_player(db, pid)
    mine = next((r for r in ov["rows"] if r["p"]["id"] == pid), None)
    if mine is None:  # inaktiv spiller: beregn alligevel
        mine = player_metrics(db, p, model.load_rounds(db, team_id()), _dev_with_att(_devrow(db, pid), pid, att_counts(db), latest_wellbeing(db)), ov["totals"])
    return dict(m=mine, avg=ov["avg"], note=model.age_note(mine["q"]) if mine["q"] else "", trend=wellbeing_chart(db, pid))


@bp.route("/", methods=["GET", "POST"])
def matrix():
    db = get_db()
    players = active_players(db)
    if request.method == "POST":
        auto = att_counts(db) is not None                 # fremmøde registreret pr. træning → tællerne beregnes
        if not auto:
            for key in ("trainings_total", "matches_total"):
                v = int_in(request.form.get(key), 0, 999)
                set_setting(db, team_id(), key, str(v) if v else "")
        for p in players:
            db.execute("INSERT OR IGNORE INTO devdata(player_id) VALUES(?)", (p["id"],))
            for f, lo, hi in NUM_FIELDS:
                if auto and f in ("trainings", "matches"):
                    continue
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


# ----------------------------------------------------------------------------- fremmøde pr. træning/kamp
def _event(db, eid):
    from flask import abort
    e = db.execute("SELECT * FROM att_events WHERE id=? AND team_id=?", (eid, team_id())).fetchone()
    if not e:
        abort(404)
    return e


@bp.route("/fremmoede", methods=["GET", "POST"])
def attendance():
    import datetime
    db = get_db()
    if request.method == "POST":
        kind = request.form.get("kind")
        day = (request.form.get("day") or "").strip()
        if kind not in ("training", "match") or not model.parse_date(day):
            flash("Vælg type og en gyldig dato.", "error")
            return redirect(url_for("devdata.attendance"))
        cur = db.execute("INSERT INTO att_events(team_id,kind,day,note,created_by) VALUES(?,?,?,?,?)",
                         (team_id(), kind, day, (request.form.get("note") or "").strip()[:200] or None, g.user["username"]))
        db.execute("INSERT INTO att_marks(event_id,player_id) SELECT ?, id FROM players WHERE team_id=? AND active=1", (cur.lastrowid, team_id()))   # alle til stede som udgangspunkt
        db.commit()
        return redirect(url_for("devdata.attendance_edit", eid=cur.lastrowid))
    rows = db.execute("SELECT e.*, (SELECT COUNT(*) FROM att_marks m WHERE m.event_id=e.id) AS present FROM att_events e WHERE e.team_id=? "
                      "ORDER BY e.day DESC, e.id DESC LIMIT 200", (team_id(),)).fetchall()
    return render_template("devdata_attendance.html", rows=rows, today=datetime.date.today().isoformat(), n_players=len(active_players(db)))


@bp.route("/fremmoede/<int:eid>", methods=["GET", "POST"])
def attendance_edit(eid):
    db = get_db()
    e = _event(db, eid)
    players = active_players(db)
    if request.method == "POST":
        ids = {int(x) for x in request.form.getlist("present") if x.isdigit()} & {p["id"] for p in players}
        db.execute("DELETE FROM att_marks WHERE event_id=?", (eid,))
        for pid in ids:
            db.execute("INSERT INTO att_marks(event_id,player_id) VALUES(?,?)", (eid, pid))
        db.commit()
        flash(f"Gemt: {len(ids)} af {len(players)} til stede.", "ok")
        return redirect(url_for("devdata.attendance"))
    present = {r["player_id"] for r in db.execute("SELECT player_id FROM att_marks WHERE event_id=?", (eid,))}
    return render_template("devdata_attendance_edit.html", e=e, players=players, present=present)


@bp.route("/fremmoede/<int:eid>/delete", methods=["POST"])
def attendance_delete(eid):
    db = get_db()
    _event(db, eid)
    db.execute("DELETE FROM att_events WHERE id=?", (eid,))
    db.commit()
    flash("Registreringen er slettet.", "ok")
    return redirect(url_for("devdata.attendance"))


# ----------------------------------------------------------------------------- trivsel over tid
def wellbeing_chart(db, pid):
    """Linjediagram: spillerens trivsel (gennemsnit af 3 spørgsmål) pr. måling mod holdets gennemsnit. None hvis under 2 målinger."""
    rows = db.execute("SELECT w.* FROM wellbeing w JOIN players p ON p.id=w.player_id WHERE p.team_id=? ORDER BY w.day", (team_id(),)).fetchall()
    days = sorted({r["day"] for r in rows if r["player_id"] == pid})
    if len(days) < 2:
        return None
    mean = lambda r: model.mean([r["t1"], r["t2"], r["t3"]])
    mine = {r["day"]: mean(r) for r in rows if r["player_id"] == pid}
    team = {d: model.mean([mean(r) for r in rows if r["day"] == d]) for d in days}
    labels = [d[8:10] + "/" + d[5:7] for d in days]
    return charts.line_chart(labels, [("Spilleren", [mine[d] for d in days], charts.COLORS[0]), ("Holdets gennemsnit", [team[d] for d in days], charts.COLORS[2])],
                             label="Trivsel over tid")


@bp.route("/trivsel", methods=["GET", "POST"])
def wellbeing():
    import datetime
    db = get_db()
    players = active_players(db)
    day = (request.values.get("day") or datetime.date.today().isoformat()).strip()
    if not model.parse_date(day):
        flash("Ugyldig dato.", "error")
        day = datetime.date.today().isoformat()
    if request.method == "POST":
        n = 0
        for p in players:
            vals = [int_in(request.form.get(f"{k}_{p['id']}"), 1, 5) for k in ("t1", "t2", "t3")]
            if all(v is None for v in vals):
                db.execute("DELETE FROM wellbeing WHERE player_id=? AND day=?", (p["id"], day))
                continue
            db.execute("INSERT INTO wellbeing(player_id,day,t1,t2,t3) VALUES(?,?,?,?,?) ON CONFLICT(player_id,day) DO UPDATE SET t1=excluded.t1,t2=excluded.t2,t3=excluded.t3",
                       (p["id"], day, *vals))
            n += 1
        audit(db, g.user["username"], "trivsel_gemt", f"{day}: {n} spillere")
        db.commit()
        flash(f"Trivsel for {n} spillere gemt.", "ok")
        return redirect(url_for("devdata.wellbeing", day=day))
    have = {r["player_id"]: r for r in db.execute("SELECT * FROM wellbeing WHERE day=? AND player_id IN (SELECT id FROM players WHERE team_id=?)", (day, team_id()))}
    days = [r["day"] for r in db.execute("SELECT DISTINCT w.day FROM wellbeing w JOIN players p ON p.id=w.player_id WHERE p.team_id=? ORDER BY w.day DESC LIMIT 20", (team_id(),))]
    return render_template("devdata_wellbeing.html", players=players, have=have, day=day, days=days, trivsel=model.TRIVSEL)
