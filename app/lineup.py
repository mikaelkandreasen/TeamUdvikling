"""Holdsætning: trænergruppen sammensætter og gemmer opstillinger for 3v3, 5v5, 8v8 og 11v11 og markerer ét idealhold pr. kamptype.
Alle opstillinger hører til det aktive hold (team_id); spillere kan kun sættes på pladser, hvis de er aktive spillere på samme hold."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from . import charts, formations, model, split as splitter
from .db import audit, get_db
from .helpers import active_players, default_round, int_in, photo_ids, positions_of, team_id

bp = Blueprint("lineup", __name__, url_prefix="/lineup")
MAX_PER_TYPE = 30
MAX_NAME = 60


def _get(db, lid):
    row = db.execute("SELECT * FROM lineups WHERE id=? AND team_id=?", (lid, team_id())).fetchone()
    if not row:
        abort(404)
    return row


def _latest_scores(db):
    rounds = model.load_rounds(db, team_id())
    res = rounds[default_round(rounds)]
    return {pid: r["samlet"] for pid, r in res.items() if r["samlet"] is not None}


def _name(raw, fallback):
    return " ".join((raw or "").split())[:MAX_NAME] or fallback


@bp.route("/")
def index():
    db = get_db()
    gt = request.args.get("type") if request.args.get("type") in formations.GAME_TYPES else formations.DEFAULT_TYPE
    rows = db.execute("SELECT l.*, (SELECT COUNT(*) FROM lineup_slots s WHERE s.lineup_id=l.id AND s.player_id IS NOT NULL) AS filled "
                      "FROM lineups l WHERE l.team_id=? AND l.game_type=? ORDER BY l.is_ideal DESC, l.updated_at DESC, l.id DESC", (team_id(), gt)).fetchall()
    return render_template("lineup_index.html", gt=gt, size=formations.GAME_TYPES[gt], types=formations.GAME_TYPES, rows=rows,
                           options=formations.FORMATIONS[gt], default=formations.DEFAULT_FORMATION[gt])


@bp.route("/new", methods=["POST"])
def new():
    db = get_db()
    gt, fm = request.form.get("game_type", ""), request.form.get("formation", "")
    if not formations.is_valid(gt, fm):
        abort(400)
    if db.execute("SELECT COUNT(*) FROM lineups WHERE team_id=? AND game_type=?", (team_id(), gt)).fetchone()[0] >= MAX_PER_TYPE:
        flash(f"Der kan højst gemmes {MAX_PER_TYPE} opstillinger pr. kamptype. Slet en gammel først.", "error")
        return redirect(url_for("lineup.index", type=gt))
    cur = db.execute("INSERT INTO lineups(team_id,name,game_type,formation,created_by,created_at,updated_at) VALUES(?,?,?,?,?,datetime('now'),datetime('now'))",
                     (team_id(), _name(request.form.get("name"), f"Opstilling {fm}"), gt, fm, g.user["username"]))
    audit(db, g.user["username"], "opstilling_oprettet", f"id={cur.lastrowid}")
    db.commit()
    return redirect(url_for("lineup.edit", lid=cur.lastrowid))


def _split_plan(db):
    """Deler truppen i A/B/C-hold efter holdprofilen (kamptype + udskiftere) og spillerniveau. Starterne placeres på standardopstillingen."""
    from .team import profile
    prof = profile(db, team_id())
    per = int_in(request.values.get("per_tier"), 1, 3) or 3
    scores = _latest_scores(db)
    players = active_players(db)
    from . import levels as levelcalc
    calc = levelcalc.calc(db, players, model.load_rounds(db, team_id()))
    plist = [dict(id=p["id"], name=p["name"], level=p["level"] or (calc.get(p["id"]) or {}).get("level"), score=scores.get(p["id"]), positions=positions_of(p)) for p in players]
    teams, left = splitter.split(plist, prof["size"], prof["subs"], per)
    fm = formations.DEFAULT_FORMATION[prof["game_type"]]
    sl = formations.slots(prof["game_type"], fm)
    byid = {p["id"]: p for p in plist}
    for t in teams:
        starters = t["players"][:prof["size"]]
        assign = formations.suggest(sl, starters, scores)
        t["slots"] = [dict(tag=s["tag"], player=byid.get(assign.get(s["i"]))) for s in sl]
        t["assign"] = assign
        t["subs"] = t["players"][prof["size"]:]
    return prof, fm, per, teams, [byid[p["id"]] for p in left]


@bp.route("/split", methods=["GET", "POST"])
def split_view():
    db = get_db()
    prof, fm, per, teams, left = _split_plan(db)
    if request.method == "POST" and request.form.get("action") == "save":
        gt = prof["game_type"]
        used = [t for t in teams if t["players"]]
        existing = db.execute("SELECT COUNT(*) FROM lineups WHERE team_id=? AND game_type=?", (team_id(), gt)).fetchone()[0]
        names = [t["name"] for t in used]
        replaced = db.execute(f"SELECT COUNT(*) FROM lineups WHERE team_id=? AND game_type=? AND name IN ({','.join('?' * len(names))})", [team_id(), gt, *names]).fetchone()[0] if names else 0
        if existing - replaced + len(used) > MAX_PER_TYPE:
            flash(f"Der kan højst gemmes {MAX_PER_TYPE} opstillinger pr. kamptype. Slet gamle først.", "error")
            return redirect(url_for("lineup.split_view", per_tier=per))
        for t in used:
            db.execute("DELETE FROM lineups WHERE team_id=? AND game_type=? AND name=?", (team_id(), gt, t["name"]))
            cur = db.execute("INSERT INTO lineups(team_id,name,game_type,formation,created_by,created_at,updated_at) VALUES(?,?,?,?,?,datetime('now'),datetime('now'))",
                             (team_id(), t["name"], gt, fm, g.user["username"]))
            for slot, pid in t["assign"].items():
                db.execute("INSERT INTO lineup_slots(lineup_id,slot,player_id) VALUES(?,?,?)", (cur.lastrowid, slot, pid))
        audit(db, g.user["username"], "holddeling_gemt", f"{len(used)} hold")
        db.commit()
        flash(f"{len(used)} opstillinger er gemt under Holdsætning ({prof['game_type']}).", "ok")
        return redirect(url_for("lineup.index", type=gt))
    return render_template("lineup_split.html", prof=prof, formation=fm, per=per, teams=teams, left=left,
                           no_levels=sum(1 for t in teams for p in t["players"] if not p.get("level")) + sum(1 for p in left if not p.get("level")))


def _view(db, L, assign, players, scores, matched_note=None):
    sl = formations.slots(L["game_type"], L["formation"])
    photos = photo_ids(db)
    pmap = {p["id"]: p for p in players}
    pos = {p["id"]: positions_of(p) for p in players}
    rows = []
    for s in sl:
        opts = []
        for p in sorted(players, key=lambda p: (-formations.fit(pos[p["id"]], s["tag"]), p["name"].lower())):
            k = formations.choice_no(pos[p["id"]], s["tag"])
            opts.append(dict(id=p["id"], text=p["name"] + (f"  ✓ valg {k}" if k else "")))
        rows.append(dict(slot=s, options=opts, chosen=assign.get(s["i"])))
    placed = []
    for s in sl:
        pid = assign.get(s["i"])
        p = pmap.get(pid)
        placed.append(dict(x=s["x"], y=s["y"], tag=s["tag"], player=None if not p else dict(
            name=p["name"], value=scores.get(pid), pid=pid, photo=url_for("players.photo_view", pid=pid) if pid in photos else None)))
    matched = sum(1 for s in sl if assign.get(s["i"]) and formations.choice_no(pos[assign[s["i"]]], s["tag"]))
    bench = [p for p in players if p["id"] not in assign.values()]
    pitch = charts.formation_pitch(L["game_type"], placed, f"{L['game_type']} {L['formation']}")
    return render_template("lineup_edit.html", L=L, rows=rows, pitch=pitch, bench=bench, photos=photos, matched=matched, filled=len(assign),
                           total=len(sl), options=formations.FORMATIONS[L["game_type"]])


@bp.route("/<int:lid>", methods=["GET", "POST"])
def edit(lid):
    db = get_db()
    L = _get(db, lid)
    players = active_players(db)
    pmap = {p["id"] for p in players}
    sl = formations.slots(L["game_type"], L["formation"])
    scores = _latest_scores(db)
    saved = {r["slot"]: r["player_id"] for r in db.execute("SELECT slot, player_id FROM lineup_slots WHERE lineup_id=?", (lid,)) if r["player_id"] in pmap}
    if request.method == "GET":
        return _view(db, L, saved, players, scores)
    action = request.form.get("action", "save")
    if action == "clear":
        flash("Banen er ryddet. Tryk Gem for at beholde det.", "ok")
        return _view(db, L, {}, players, scores)
    if action in ("suggest", "suggest_scores"):
        cands = [dict(id=p["id"], positions=positions_of(p)) for p in players]
        assign = formations.suggest(sl, cands, scores if action == "suggest_scores" else None)
        flash("Forslag indsat ud fra spillernes positionsvalg" + (" og seneste samlede score" if action == "suggest_scores" else "")
              + ". Ret frit, og tryk Gem for at beholde det.", "ok")
        return _view(db, L, assign, players, scores)
    assign, problem = {}, None
    for s in sl:
        raw = request.form.get(f"slot{s['i']}", "")
        if not raw:
            continue
        pid = int_in(raw, 1, 2 ** 31)
        if pid not in pmap:
            abort(400)                                          # kun aktive spillere på dette hold
        if pid in assign.values():
            problem = "Samme spiller er valgt til flere pladser. Ret og gem igen."
        assign[s["i"]] = pid
    if problem:
        flash(problem, "error")
        return _view(db, L, assign, players, scores)
    db.execute("DELETE FROM lineup_slots WHERE lineup_id=?", (lid,))
    db.executemany("INSERT INTO lineup_slots(lineup_id,slot,player_id) VALUES(?,?,?)", [(lid, i, pid) for i, pid in assign.items()])
    db.execute("UPDATE lineups SET updated_at=datetime('now') WHERE id=?", (lid,))
    audit(db, g.user["username"], "opstilling_gemt", f"id={lid}")
    db.commit()
    flash("Opstillingen er gemt.", "ok")
    return redirect(url_for("lineup.edit", lid=lid))


@bp.route("/<int:lid>/meta", methods=["POST"])
def meta(lid):
    db = get_db()
    L = _get(db, lid)
    fm = request.form.get("formation", L["formation"])
    if not formations.is_valid(L["game_type"], fm):
        abort(400)
    if fm != L["formation"]:                                    # ny opstilling = nye pladser → spillerne sættes forfra
        db.execute("DELETE FROM lineup_slots WHERE lineup_id=?", (lid,))
        flash("Opstillingen er ændret, så pladserne er ryddet.", "ok")
    db.execute("UPDATE lineups SET name=?, formation=?, updated_at=datetime('now') WHERE id=?", (_name(request.form.get("name"), L["name"]), fm, lid))
    audit(db, g.user["username"], "opstilling_rettet", f"id={lid}")
    db.commit()
    return redirect(url_for("lineup.edit", lid=lid))


@bp.route("/<int:lid>/ideal", methods=["POST"])
def ideal(lid):
    db = get_db()
    L = _get(db, lid)
    make = 0 if L["is_ideal"] else 1
    if make:                                                    # ét idealhold pr. hold og kamptype
        db.execute("UPDATE lineups SET is_ideal=0 WHERE team_id=? AND game_type=?", (team_id(), L["game_type"]))
    db.execute("UPDATE lineups SET is_ideal=? WHERE id=?", (make, lid))
    audit(db, g.user["username"], "opstilling_ideal" if make else "opstilling_ideal_fjernet", f"id={lid}")
    db.commit()
    flash("Markeret som idealhold." if make else "Idealhold-markering fjernet.", "ok")
    return redirect(url_for("lineup.edit", lid=lid))


@bp.route("/<int:lid>/delete", methods=["POST"])
def delete(lid):
    db = get_db()
    L = _get(db, lid)
    if request.form.get("confirm") != "ja":
        flash("Sletning kræver bekræftelse.", "error")
        return redirect(url_for("lineup.edit", lid=lid))
    db.execute("DELETE FROM lineups WHERE id=? AND team_id=?", (lid, team_id()))
    audit(db, g.user["username"], "opstilling_slettet", f"id={lid}")
    db.commit()
    flash("Opstillingen er slettet.", "ok")
    return redirect(url_for("lineup.index", type=L["game_type"]))
