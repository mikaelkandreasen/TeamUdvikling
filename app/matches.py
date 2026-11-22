"""Kampe: sæt spillere på positioner pr. periode, så spilletid pr. spiller og position kan summeres over tid (hvide pletter)."""
import datetime

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from . import formations, model
from .db import audit, get_db
from .helpers import active_players, int_in, team_id
from .team import profile

bp = Blueprint("matches", __name__, url_prefix="/kampe")

GROUPS = (("GK", "Målmand"), ("DEF", "Forsvar"), ("MID", "Midtbane"), ("WING", "Kant"), ("ATT", "Angreb"))


def group_of(tag):
    return formations.GROUP.get(tag, "ALL")


def _get(db, mid):
    m = db.execute("SELECT * FROM matches WHERE id=? AND team_id=?", (mid, team_id())).fetchone()
    if not m:
        abort(404)
    return m


def _labels(sl):
    """Pladsnavne; dubletter nummereres (Midtbane 1, Midtbane 2)."""
    count = {}
    for s in sl:
        count[s["tag"]] = count.get(s["tag"], 0) + 1
    seen, out = {}, []
    for s in sl:
        seen[s["tag"]] = seen.get(s["tag"], 0) + 1
        out.append(s["tag"] if count[s["tag"]] == 1 else f"{s['tag']} {seen[s['tag']]}")
    return out


def _form(data):
    day = (data.get("day") or "").strip()
    gt = data.get("game_type") or formations.DEFAULT_TYPE
    fm = data.get("formation") or formations.DEFAULT_FORMATION.get(gt, "")
    periods = int_in(data.get("periods"), 1, 8) or 4
    pmin = int_in(data.get("period_min"), 1, 60) or 12
    if not model.parse_date(day) or not formations.is_valid(gt, fm):
        return None
    return dict(day=day, opponent=(data.get("opponent") or "").strip()[:60], game_type=gt, formation=fm, periods=periods, period_min=pmin)


@bp.route("/")
def index():
    db = get_db()
    rows = db.execute("SELECT m.*, (SELECT COUNT(*) FROM match_slots s WHERE s.match_id=m.id) AS filled FROM matches m WHERE m.team_id=? ORDER BY m.day DESC, m.id DESC", (team_id(),)).fetchall()
    return render_template("matches.html", rows=rows, types=formations.GAME_TYPES, options=formations.FORMATIONS, default_type=profile(db, team_id())["game_type"],
                           defaults=formations.DEFAULT_FORMATION, today=datetime.date.today().isoformat(), size=formations.GAME_TYPES)


@bp.route("/ny", methods=["POST"])
def new():
    f = _form(request.form)
    if not f:
        flash("Angiv en gyldig dato og opstilling.", "error")
        return redirect(url_for("matches.index"))
    db = get_db()
    cur = db.execute("INSERT INTO matches(team_id,day,opponent,game_type,formation,periods,period_min,created_by) VALUES(?,?,?,?,?,?,?,?)",
                     (team_id(), f["day"], f["opponent"], f["game_type"], f["formation"], f["periods"], f["period_min"], g.user["username"]))
    audit(db, g.user["username"], "kamp_oprettet", f"id={cur.lastrowid}")
    db.commit()
    return redirect(url_for("matches.edit", mid=cur.lastrowid))


def _view(db, m, assign, players):
    sl = formations.slots(m["game_type"], m["formation"])
    labels = _labels(sl)
    pmin = m["period_min"]
    minutes = {p["id"]: 0 for p in players}
    for (per, slot), pid in assign.items():
        if pid in minutes:
            minutes[pid] += pmin
    bench = {per: [p for p in players if p["id"] not in {pid for (pp, _s), pid in assign.items() if pp == per}] for per in range(m["periods"])}
    return render_template("match_edit.html", m=m, sl=sl, labels=labels, assign=assign, players=players, minutes=minutes, bench=bench, total=m["periods"] * pmin)


@bp.route("/<int:mid>", methods=["GET", "POST"])
def edit(mid):
    db = get_db()
    m = _get(db, mid)
    players = active_players(db)
    pmap = {p["id"] for p in players}
    sl = formations.slots(m["game_type"], m["formation"])
    saved = {(r["period"], r["slot"]): r["player_id"] for r in db.execute("SELECT period, slot, player_id FROM match_slots WHERE match_id=?", (mid,)) if r["player_id"] in pmap}
    if request.method == "GET":
        return _view(db, m, saved, players)
    action = request.form.get("action", "save")
    assign, problem = {}, None
    for per in range(m["periods"]):
        used = set()
        for s in sl:
            raw = request.form.get(f"p{per}s{s['i']}", "")
            if not raw:
                continue
            pid = int_in(raw, 1, 2 ** 31)
            if pid not in pmap:
                abort(400)                                      # kun aktive spillere på dette hold
            if pid in used:
                problem = f"Samme spiller er valgt to gange i periode {per + 1}. Ret og gem igen."
            used.add(pid)
            assign[(per, s["i"])] = pid
    if action == "copy1":
        assign = {(per, i): pid for (p0, i), pid in assign.items() if p0 == 0 for per in range(m["periods"])}
        flash("Periode 1 er kopieret til alle perioder. Ret frit, og tryk Gem.", "ok")
        return _view(db, m, assign, players)
    if problem:
        flash(problem, "error")
        return _view(db, m, assign, players)
    db.execute("DELETE FROM match_slots WHERE match_id=?", (mid,))
    db.executemany("INSERT INTO match_slots(match_id,period,slot,player_id) VALUES(?,?,?,?)", [(mid, per, i, pid) for (per, i), pid in assign.items()])
    audit(db, g.user["username"], "kamp_gemt", f"id={mid}")
    db.commit()
    flash("Kampen er gemt.", "ok")
    return redirect(url_for("matches.edit", mid=mid))


@bp.route("/<int:mid>/meta", methods=["POST"])
def meta(mid):
    db = get_db()
    m = _get(db, mid)
    f = _form(dict(request.form, game_type=m["game_type"], formation=m["formation"]))
    if not f:
        flash("Angiv en gyldig dato.", "error")
        return redirect(url_for("matches.edit", mid=mid))
    db.execute("UPDATE matches SET day=?, opponent=?, periods=?, period_min=? WHERE id=?", (f["day"], f["opponent"], f["periods"], f["period_min"], mid))
    db.execute("DELETE FROM match_slots WHERE match_id=? AND period>=?", (mid, f["periods"]))
    db.commit()
    flash("Kampen er opdateret.", "ok")
    return redirect(url_for("matches.edit", mid=mid))


@bp.route("/<int:mid>/slet", methods=["POST"])
def delete(mid):
    db = get_db()
    _get(db, mid)
    db.execute("DELETE FROM matches WHERE id=?", (mid,))
    audit(db, g.user["username"], "kamp_slettet", f"id={mid}")
    db.commit()
    flash("Kampen er slettet.", "ok")
    return redirect(url_for("matches.index"))


def overview_data(db, tid, players, last=None):
    """Spilletid pr. spiller og positionsgruppe over kampene (nyeste `last` kampe, ellers alle). Hvid plet = 0 minutter i en gruppe, holdet har brugt."""
    ms = db.execute("SELECT * FROM matches WHERE team_id=? ORDER BY day DESC, id DESC", (tid,)).fetchall()
    ms = [m for m in ms if db.execute("SELECT 1 FROM match_slots WHERE match_id=?", (m["id"],)).fetchone()]
    if last:
        ms = ms[:last]
    ids = {p["id"] for p in players}
    stat = {p["id"]: dict(p=p, games=set(), total=0, by={k: 0 for k, _ in GROUPS}) for p in players}
    team_by = {k: 0 for k, _ in GROUPS}
    for m in ms:
        labels = formations.slots(m["game_type"], m["formation"])
        for r in db.execute("SELECT period, slot, player_id FROM match_slots WHERE match_id=?", (m["id"],)):
            if r["player_id"] not in ids or r["slot"] >= len(labels):
                continue
            grp = group_of(labels[r["slot"]]["tag"])
            if grp not in team_by:
                continue
            st = stat[r["player_id"]]
            st["games"].add(m["id"]); st["total"] += m["period_min"]; st["by"][grp] += m["period_min"]; team_by[grp] += m["period_min"]
    used = [k for k, _ in GROUPS if team_by[k] > 0]
    rows = []
    played = [s for s in stat.values() if s["games"]]
    avg = (sum(s["total"] for s in played) / len(played)) if played else 0
    for s in stat.values():
        s["n"] = len(s["games"])
        s["missing"] = [lab for k, lab in GROUPS if k in used and s["by"][k] == 0]
        s["low"] = bool(avg) and s["total"] < 0.7 * avg
        rows.append(s)
    rows.sort(key=lambda s: s["p"]["name"])
    return dict(rows=rows, used=used, n_matches=len(ms), avg=round(avg), groups=GROUPS)


@bp.route("/overblik")
def overview():
    db = get_db()
    last = request.args.get("sidste", type=int)
    return render_template("match_overview.html", last=last if last in (3, 5, 10) else None, **overview_data(db, team_id(), active_players(db), last if last in (3, 5, 10) else None))
