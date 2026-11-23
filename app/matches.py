"""Kampe: sæt spillere på positioner pr. periode, så spilletid pr. spiller og position kan summeres over tid (hvide pletter)."""
import datetime
import re

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from . import club, formations, ical, model, suggest
from .db import audit, get_db, get_setting, set_setting
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
                           defaults=formations.DEFAULT_FORMATION, has_ical=bool(get_setting(db, team_id(), "ical_url")), today=datetime.date.today().isoformat(), size=formations.GAME_TYPES)


_SPLIT = re.compile(r"\s+(?:-|–|—|vs\.?|v|mod)\s+", re.I)


def guess_opponent(summary, own_names):
    """Modstanderen ud fra en titel som 'Pigehold: Virring IF - Skanderborg': delen, der ikke ligner eget hold/klub. Returnerer (navn, ligner_kamp)."""
    s = re.sub(r"^\s*(kamp|[A-ZÆØÅ]\d{1,2}\b[^:]*):\s*", "", summary or "").strip()
    parts = [p.strip() for p in _SPLIT.split(s) if p.strip()]
    if len(parts) < 2:
        return s[:60], False
    own = [n.lower() for n in own_names if n and len(n) >= 3]
    rest = [p for p in parts if not any(o in p.lower() or p.lower() in o for o in own)]
    return (rest[0] if rest else parts[-1])[:60], True


FEED_MIN_SECONDS = 60          # højst ét udgående kald pr. hold pr. minut; ellers bruges sidst hentede


def _feed_events(db, url):
    """Kalenderens aftaler. Genbruger hentningen fra det seneste minut, så siden ikke kan bruges til at hamre på en fremmed server."""
    import json
    import time
    now = int(time.time())
    try:
        last = int(get_setting(db, team_id(), "ical_fetched_at") or 0)
    except ValueError:
        last = 0
    if now - last < FEED_MIN_SECONDS:
        try:
            return json.loads(get_setting(db, team_id(), "ical_suggest_cache") or "[]")
        except ValueError:
            pass
    try:
        events = ical.parse(ical.fetch(url))[:500]
    except ical.FeedError as exc:
        flash(str(exc), "error")
        return None
    for e in events:
        e["uid"] = e["uid"] or f"{e['day']}|{e['time']}|{e['summary']}"[:200]
    set_setting(db, team_id(), "ical_fetched_at", str(now))
    set_setting(db, team_id(), "ical_suggest_cache", json.dumps(events))
    db.commit()
    return events


@bp.route("/forslag")
def suggestions():
    """Henter kalenderen og viser kommende kampe, der endnu ikke er oprettet."""
    db = get_db()
    url = get_setting(db, team_id(), "ical_url")
    if not url:
        flash("Tilføj først holdets kalenderlink under Holdindstillinger.", "error")
        return redirect(url_for("matches.index"))
    events = _feed_events(db, url)
    if events is None:
        return redirect(url_for("matches.index"))
    today = datetime.date.today().isoformat()
    have = db.execute("SELECT ical_uid, day FROM matches WHERE team_id=?", (team_id(),)).fetchall()
    uids, days = {r["ical_uid"] for r in have if r["ical_uid"]}, {r["day"] for r in have}
    own = [g.team["name"], club.info()["name"], (club.info()["name"] or "").split(" ")[0]]
    rows = []
    for e in events:
        if e["day"] < today or e["uid"] in uids:
            continue
        opp, looks = guess_opponent(e["summary"], own)
        rows.append(dict(e, opp=opp, same_day=e["day"] in days, looks_match=looks or ical.kind_of(e["summary"]) == "match"))
    return render_template("matches_ical.html", rows=rows[:40], total=len(rows), changes=_feed_changes(db, events, today))


_NOTE_TIME = re.compile(r"kl\. (\d\d:\d\d)")


def _feed_changes(db, events, today):
    """Allerede oprettede kampe (fra kalenderen), hvor kalenderen siden er ændret: flyttet dag/tid, eller væk (aflyst) – I-10."""
    feed = {e["uid"]: e for e in events}
    out = []
    for m in db.execute("SELECT id, day, opponent, note, ical_uid FROM matches WHERE team_id=? AND ical_uid IS NOT NULL AND day>=? ORDER BY day", (team_id(), today)):
        e = feed.get(m["ical_uid"])
        if e is None:
            out.append(dict(kind="removed", m=m))
            continue
        old = _NOTE_TIME.search(m["note"] or "")
        new_time = (e.get("time") or "")[:5]
        if e["day"] != m["day"] or (old and new_time and old.group(1) != new_time):
            out.append(dict(kind="moved", m=m, day=e["day"], time=new_time, old_time=old.group(1) if old else ""))
    return out


@bp.route("/<int:mid>/kalender", methods=["POST"])
def ical_update(mid):
    """Opdatér dato/tid på en oprettet kamp efter kalenderen. Værdierne slås op i kalenderen – formularen bestemmer dem ikke."""
    db = get_db()
    m = _get(db, mid)
    url = get_setting(db, team_id(), "ical_url")
    events = _feed_events(db, url) if url and m["ical_uid"] else None
    e = next((x for x in events or [] if x["uid"] == m["ical_uid"]), None)
    if not e or not model.parse_date(e["day"]):
        flash("Kampen findes ikke længere i kalenderen – ret den selv eller slet den.", "error")
        return redirect(url_for("matches.suggestions"))
    note = m["note"] or ""
    t = (e.get("time") or "")[:5]
    if t:
        note = _NOTE_TIME.sub(f"kl. {t}", note) if _NOTE_TIME.search(note) else " · ".join(x for x in (f"kl. {t}", note) if x)
    db.execute("UPDATE matches SET day=?, note=? WHERE id=?", (e["day"], note[:300], mid))
    audit(db, g.user["username"], "kamp_fra_kalender", f"id={mid}")
    db.commit()
    flash("Kampen er opdateret efter kalenderen.", "ok")
    return redirect(url_for("matches.suggestions"))


@bp.route("/importer", methods=["POST"])
def import_matches():
    db = get_db()
    prof = profile(db, team_id())
    gt = prof["game_type"]
    fm = formations.DEFAULT_FORMATION.get(gt) or formations.DEFAULT_FORMATION.get(formations.DEFAULT_TYPE)
    n = 0
    for i in request.form.getlist("pick")[:60]:
        if not i.isdigit():
            continue
        day = (request.form.get(f"day{i}") or "").strip()
        uid = (request.form.get(f"uid{i}") or "").strip()[:200]
        if not model.parse_date(day) or not uid:
            continue
        if db.execute("SELECT 1 FROM matches WHERE team_id=? AND ical_uid=?", (team_id(), uid)).fetchone():
            continue
        time, place = (request.form.get(f"time{i}") or "").strip()[:5], (request.form.get(f"loc{i}") or "").strip()[:200]
        note = " · ".join(x for x in ((f"kl. {time}" if time else ""), place) if x)
        db.execute("INSERT INTO matches(team_id,day,opponent,game_type,formation,periods,period_min,note,created_by,ical_uid) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (team_id(), day, (request.form.get(f"opp{i}") or "").strip()[:60], gt, fm, 4, 12, note, g.user["username"], uid))
        n += 1
    audit(db, g.user["username"], "kampe_importeret", f"antal={n}")
    db.commit()
    flash(f"{n} kampe oprettet. Sæt spillere på under hver kamp." if n else "Ingen kampe valgt.", "ok" if n else "error")
    return redirect(url_for("matches.index"))


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


def _history(db, tid, players, exclude_mid):
    """Minutter pr. spiller og positionsgruppe i tidligere kampe (uden den aktuelle)."""
    ids = {p["id"] for p in players}
    hist = {p["id"]: {} for p in players}
    for m in db.execute("SELECT * FROM matches WHERE team_id=? AND id<>?", (tid, exclude_mid)).fetchall():
        labels = formations.slots(m["game_type"], m["formation"])
        for r in db.execute("SELECT slot, player_id FROM match_slots WHERE match_id=?", (m["id"],)):
            if r["player_id"] in ids and r["slot"] < len(labels):
                k = group_of(labels[r["slot"]]["tag"])
                hist[r["player_id"]][k] = hist[r["player_id"]].get(k, 0) + m["period_min"]
    return hist


def attendance_absent(db, tid, day, pids):
    """Spillere, der ikke var til stede ifølge fremmøde-registreringen af en kamp samme dag (tom, hvis kampen ikke er registreret) – I-01."""
    if not db.execute("SELECT 1 FROM att_events WHERE team_id=? AND day=? AND kind='match'", (tid, day)).fetchone():
        return set()
    present = {r["player_id"] for r in db.execute("SELECT m.player_id FROM att_marks m JOIN att_events e ON e.id=m.event_id WHERE e.team_id=? AND e.day=? AND e.kind='match'", (tid, day))}
    return {pid for pid in pids if pid not in present}


def _view(db, m, assign, players, absent=(), use_gk=True):
    sl = formations.slots(m["game_type"], m["formation"])
    labels = _labels(sl)
    pmin = m["period_min"]
    minutes = {p["id"]: 0 for p in players}
    for (per, slot), pid in assign.items():
        if pid in minutes:
            minutes[pid] += pmin
    away = attendance_absent(db, m["team_id"], m["day"], minutes)
    bench = {per: [p for p in players if p["id"] not in away and p["id"] not in {pid for (pp, _s), pid in assign.items() if pp == per}] for per in range(m["periods"])}
    return render_template("match_edit.html", m=m, sl=sl, labels=labels, assign=assign, players=players, minutes=minutes, bench=bench, total=m["periods"] * pmin,
                           absent=set(absent) | away, away=[p for p in players if p["id"] in away], use_gk=use_gk)


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
    if action == "suggest":
        absent = {pid for pid in (int_in(x, 1, 2 ** 31) for x in request.form.getlist("absent")) if pid in pmap}
        use_gk = bool(request.form.get("use_gk"))
        hist = _history(db, team_id(), players, mid)
        assign, filled = suggest.suggest(sl, group_of, [p["id"] for p in players], hist, m["periods"], m["period_min"], absent, use_gk)
        names, labels = {p["id"]: p["name"] for p in players}, dict(GROUPS)
        msg = "Forslag lavet – tryk Gem kamp, hvis du vil beholde det."
        if filled:
            msg += " Nye positioner: " + ", ".join(f"{names[pid]} ({labels.get(k, k).lower()})" for pid, k in filled[:12]) + "."
        flash(msg, "ok")
        return _view(db, m, assign, players, absent, use_gk)
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
    stat = {p["id"]: dict(p=p, games=set(), total=0, by={k: 0 for k, _ in GROUPS}, away=0) for p in players}
    team_by = {k: 0 for k, _ in GROUPS}
    for m in ms:
        for pid in attendance_absent(db, tid, m["day"], ids):
            stat[pid]["away"] += 1                      # var ikke med (fremmøde) – tæller ikke som bænk
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
    per_game = [s["total"] / (len(ms) - s["away"]) for s in played if len(ms) - s["away"] > 0]
    avg_pg = (sum(per_game) / len(per_game)) if per_game else 0
    for s in stat.values():
        s["n"] = len(s["games"])
        avail = len(ms) - s["away"]                     # kampe spilleren var med til
        s["avail"] = avail
        s["missing"] = [lab for k, lab in GROUPS if k in used and s["by"][k] == 0 and avail > 0]
        s["low"] = bool(avg_pg) and avail > 0 and s["total"] / avail < 0.7 * avg_pg
        rows.append(s)
    rows.sort(key=lambda s: s["p"]["name"])
    return dict(rows=rows, used=used, n_matches=len(ms), avg=round(avg), groups=GROUPS)


@bp.route("/overblik")
def overview():
    db = get_db()
    last = request.args.get("sidste", type=int)
    return render_template("match_overview.html", last=last if last in (3, 5, 10) else None, **overview_data(db, team_id(), active_players(db), last if last in (3, 5, 10) else None))
