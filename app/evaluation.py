"""Evaluering (4 runder x trænere x 24 kriterier), teamoversigt, udvikling, positioner, områder og spillerprofil."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from . import charts, model
from .db import get_db
from .team import team_criteria
from . import transfer
from .helpers import active_players, default_round, get_player, int_in, neighbours, photo_ids, round_info, round_window, team_id, touch_round_opened, valid_choice

bp = Blueprint("evaluation", __name__)
POSITION_TYPES = {"primaer": ("position", "Valg 1"), "sekundaer": ("position2", "Valg 2"), "tredje": ("position3", "Valg 3"), "fjerde": ("position4", "Valg 4")}


def _open_roles(raw):
    """Hvilke spillertyper (rollepaneler) der er åbne. None = ikke angivet → første er åben. Ugyldigt ignoreres."""
    if raw is None:
        return None
    out = []
    for part in raw.split(",")[:len(model.ROLES)]:
        i = int_in(part, 0, len(model.ROLES) - 1)
        if i is not None and i not in out:
            out.append(i)
    return out


def _rnd(rnd):
    if rnd not in g.rounds:
        abort(404)
    return rnd


@bp.route("/eval")
def eval_home():
    db = get_db()
    players = active_players(db)
    mine = {r: {} for r in g.rounds}
    for row in db.execute("SELECT round, player_id, COUNT(*) n FROM evaluations WHERE trainer_id=? GROUP BY round, player_id", (g.user["id"],)):
        mine[row["round"]][row["player_id"]] = row["n"]
    prog = []
    for info in round_info(db):
        done = sum(1 for p in players if mine[info["no"]].get(p["id"]) == model.N_CRIT)
        started = sum(1 for p in players if 0 < mine[info["no"]].get(p["id"], 0) < model.N_CRIT)
        prog.append(dict(info, done=done, started=started, total=len(players)))
    shown = round_window(prog)
    show_all = request.args.get("alle") == "1"
    return render_template("eval_home.html", prog=prog if show_all else [r for r in prog if r["no"] in shown], total=len(prog), show_all=show_all)


@bp.route("/eval/<int:rnd>")
def eval_round(rnd):
    _rnd(rnd)
    db = get_db()
    players = active_players(db)
    mine = {r["player_id"]: r["n"] for r in db.execute(
        "SELECT player_id, COUNT(*) n FROM evaluations WHERE round=? AND trainer_id=? GROUP BY player_id", (rnd, g.user["id"]))}
    others = {r["player_id"]: r["n"] for r in db.execute(
        "SELECT player_id, COUNT(DISTINCT trainer_id) n FROM evaluations WHERE round=? GROUP BY player_id", (rnd,))}
    info = round_info(db)[rnd - 1]
    return render_template("eval_round.html", rnd=rnd, info=info, players=players, mine=mine, others=others)


@bp.route("/eval/<int:rnd>/<int:pid>", methods=["GET", "POST"])
def eval_form(rnd, pid):
    _rnd(rnd)
    db = get_db()
    p = get_player(db, pid)
    players = active_players(db)
    prev_id, next_id = neighbours(players, pid)
    info = round_info(db)[rnd - 1]
    if request.method == "POST":
        if info["closed"]:
            flash(f"{info['label']} er lukket for indtastning (lukkede {info['closes']}). En holdansvarlig kan genåbne den.", "error")
            return redirect(url_for("evaluation.eval_form", rnd=rnd, pid=pid))
        touch_round_opened(db, rnd)
        saved = 0
        for c in model.CRITERIA:
            val = int_in(request.form.get(f"c{c['idx']}"), 1, 5)
            if val:
                db.execute("INSERT INTO evaluations(round,player_id,trainer_id,crit,score) VALUES(?,?,?,?,?) "
                           "ON CONFLICT(round,player_id,trainer_id,crit) DO UPDATE SET score=excluded.score",
                           (rnd, pid, g.user["id"], c["idx"], val))
                saved += 1
            else:
                db.execute("DELETE FROM evaluations WHERE round=? AND player_id=? AND trainer_id=? AND crit=?",
                           (rnd, pid, g.user["id"], c["idx"]))
        if "dbu_present" in request.form:
            ticks = sorted({f"{k}.{request.form.get('dbu_' + k)}" for k, _, _ in model.DBU_ITEMS} & model.DBU_KEYS)
            db.execute("DELETE FROM dbu_checks WHERE round=? AND player_id=? AND trainer_id=?", (rnd, pid, g.user["id"]))
            db.executemany("INSERT INTO dbu_checks(round,player_id,trainer_id,item) VALUES(?,?,?,?)", [(rnd, pid, g.user["id"], k) for k in ticks])
        if "level" in request.form:
            lv = request.form.get("level")
            if lv in model.LEVELS:
                db.execute("INSERT INTO level_ratings(round,player_id,trainer_id,level) VALUES(?,?,?,?) "
                           "ON CONFLICT(round,player_id,trainer_id) DO UPDATE SET level=excluded.level", (rnd, pid, g.user["id"], lv))
            else:
                db.execute("DELETE FROM level_ratings WHERE round=? AND player_id=? AND trainer_id=?", (rnd, pid, g.user["id"]))
        db.commit()
        flash(f"Gemt ({saved} af {model.N_CRIT} kriterier).", "ok")
        keep = _open_roles(request.form.get("open"))
        extra = {} if keep is None else {"open": ",".join(str(i) for i in keep)}
        if request.form.get("go") == "next" and next_id:
            return redirect(url_for("evaluation.eval_form", rnd=rnd, pid=next_id, **extra))
        return redirect(url_for("evaluation.eval_round", rnd=rnd))
    scores = {r["crit"]: r["score"] for r in db.execute(
        "SELECT crit, score FROM evaluations WHERE round=? AND player_id=? AND trainer_id=?", (rnd, pid, g.user["id"]))}
    mylevel = db.execute("SELECT level FROM level_ratings WHERE round=? AND player_id=? AND trainer_id=?", (rnd, pid, g.user["id"])).fetchone()
    dbu = {r["item"] for r in db.execute("SELECT item FROM dbu_checks WHERE round=? AND player_id=? AND trainer_id=?", (rnd, pid, g.user["id"]))}
    return render_template("eval_form.html", assist_in=g.user["id"] not in model.excluded_assistants(db, team_id()).get(rnd, ()), rnd=rnd, p=p, scores=scores, dbu=dbu, dbu_done={x.split(".")[0] for x in dbu}, dbu_res=model.dbu_result(dbu), mylevel=mylevel["level"] if mylevel else None, info=info,
                           prev_id=prev_id, next_id=next_id, criteria=team_criteria(db, team_id()),
                           open_roles=_open_roles(request.args.get("open")))


@bp.route("/overview")
@bp.route("/overview/<int:rnd>")
def team(rnd=None):
    db = get_db()
    rounds = model.load_rounds(db, team_id())
    rnd = default_round(rounds, rnd)
    players = active_players(db)
    res = rounds[rnd]
    rows = [dict(p=p, r=res.get(p["id"])) for p in players]
    avg = [model.mean([x["r"]["roles"][i] for x in rows if x["r"]]) for i in range(len(model.ROLES))]
    avg_samlet = model.mean([x["r"]["samlet"] for x in rows if x["r"]])
    return render_template("team.html", rnd=rnd, rounds_info=round_info(db), rows=rows, avg=avg, avg_samlet=avg_samlet)


@bp.route("/development")
def development():
    db = get_db()
    rounds = model.load_rounds(db, team_id())
    players = active_players(db)
    rows = []
    for p in players:
        vals = [rounds[r].get(p["id"], {}).get("samlet") for r in g.rounds]
        present = [v for v in vals if v is not None]
        d_last = present[-1] - present[-2] if len(present) >= 2 else None
        d_total = present[-1] - present[0] if len(present) >= 2 else None
        rows.append(dict(p=p, vals=vals, d_last=d_last, d_total=d_total))
    _roles, _skills, samlet = model.area_development(rounds, [p["id"] for p in players])
    chart = charts.line_chart([i["label"] for i in round_info(db)], [("Holdets samlede gennemsnit", [samlet[r] for r in g.rounds], charts.COLORS[0])],
                              label="Holdets samlede udvikling")
    return render_template("development.html", rows=rows, chart=chart, rounds_info=round_info(db))


@bp.route("/development/position")
def position_view():
    db = get_db()
    rounds = model.load_rounds(db, team_id())
    rnd = default_round(rounds, request.args.get("runde", type=int))
    type_key = request.args.get("type") if request.args.get("type") in POSITION_TYPES else "primaer"
    kind = POSITION_TYPES[type_key][0]
    pos = valid_choice(request.args.get("pos", ""), model.POSITIONS)
    photos = photo_ids(db)
    players = [p for p in active_players(db) if (not pos or p[kind] == pos) and (kind == "position" or p[kind])]
    items = []
    for p in players:
        res = rounds[rnd].get(p["id"])
        items.append(dict(p=p, samlet=res["samlet"] if res else None, roles=res["roles"] if res else [None] * 4))
    pitch = charts.pitch([dict(name=i["p"]["name"], position=i["p"][kind] or "Allround", value=i["samlet"], pid=i["p"]["id"],
                               photo=url_for("players.photo_view", pid=i["p"]["id"]) if i["p"]["id"] in photos else None) for i in items])
    return render_template("position.html", items=items, pitch=pitch, rnd=rnd, kind=kind, type_key=type_key, pos=pos, rounds_info=round_info(db),
                           type_choices=[(k, v[1]) for k, v in POSITION_TYPES.items()], photos=photos)


@bp.route("/areas")
def areas():
    db = get_db()
    rounds = model.load_rounds(db, team_id())
    players = active_players(db)
    roles, skills, samlet = model.area_development(rounds, [p["id"] for p in players])
    labels = [i["label"] for i in round_info(db)]
    role_chart = charts.line_chart(labels, [(model.ROLES[i], [roles[r][i] for r in g.rounds], charts.COLORS[i]) for i in range(4)],
                                   label="Udvikling pr. rolle")
    skill_chart = charts.line_chart(labels, [(model.SKILLS[i], [skills[r][i] for r in g.rounds],
                                              (charts.COLORS + ["#c0392b", "#16a085"])[i]) for i in range(6)], label="Udvikling pr. nøglefærdighed")
    latest_r = default_round(rounds)
    grid = [[model.mean([rounds[latest_r][p["id"]]["crit"][r * 6 + s] for p in players if p["id"] in rounds[latest_r]])
             for s in range(6)] for r in range(4)]
    return render_template("areas.html", roles=roles, skills=skills, role_chart=role_chart, skill_chart=skill_chart,
                           grid=grid, latest_r=latest_r, rounds_info=round_info(db))


def complete_rounds(db, rounds):
    """Runder hvor ALLE aktive spillere har fået en samlet score – kun disse vises i profilerne."""
    ids = [p["id"] for p in active_players(db)]
    return [r for r in g.rounds if ids and all((rounds[r].get(i) or {}).get("samlet") is not None for i in ids)]


def profile_data(db, p, rounds, rnd=None, show_all=False):
    """Samler alt til spillerprofil/rapport. Kun færdige runder (alle spillere evalueret) vises: som standard de 2 seneste."""
    pid = p["id"]
    done = [r for r in complete_rounds(db, rounds) if rounds[r].get(pid)]
    shown = done if show_all else done[-2:]
    rnd = rnd if rnd in shown else (shown[-1] if shown else None)
    res = rounds[rnd].get(pid) if rnd else None
    prev_r = next((r for r in reversed(shown) if rnd and r < rnd), None)
    prev = rounds[prev_r].get(pid) if prev_r else None
    allinfos = round_info(db)
    infos = [allinfos[r - 1] for r in shown]
    series = []
    if prev:
        series.append((allinfos[prev_r - 1]["label"], prev["roles"], "#9aa5b1"))
    if res:
        series.append((allinfos[rnd - 1]["label"], res["roles"], charts.COLORS[0]))
    radar = charts.radar(model.ROLES, series, label=f"Roller – {p['name']}") if series else None
    crit_rows = [dict(c=c, vals=[rounds[r].get(pid, {}).get("crit", [None] * 24)[c["idx"]] for r in shown]) for c in model.CRITERIA]
    ranked = sorted([(c, res["crit"][c["idx"]]) for c in model.CRITERIA if res and res["crit"][c["idx"]] is not None], key=lambda x: x[1])
    changes = None
    if res and prev and res["samlet"] is not None and prev["samlet"] is not None:
        diffs = [(c, res["crit"][c["idx"]] - prev["crit"][c["idx"]]) for c in model.CRITERIA
                 if res["crit"][c["idx"]] is not None and prev["crit"][c["idx"]] is not None]
        up = sorted([d for d in diffs if d[1] >= 0.5], key=lambda d: -d[1])[:3]
        down = sorted([d for d in diffs if d[1] <= -0.5], key=lambda d: d[1])[:3]
        changes = dict(prev_label=allinfos[prev_r - 1]["label"], total=res["samlet"] - prev["samlet"], up=up, down=down)
    return dict(rnd=rnd, res=res, prev=prev, changes=changes, radar=radar, crit_rows=crit_rows, infos=infos,
                weakest=ranked[:3], strongest=list(reversed(ranked[-3:])), show_all=show_all, more=len(done) - len(shown),
                role_rows=[dict(role=model.ROLES[i], vals=[rounds[r].get(pid, {}).get("roles", [None] * 4)[i] for r in shown]) for i in range(4)],
                samlet=[rounds[r].get(pid, {}).get("samlet") for r in shown], history=transfer.history(db, pid))


@bp.route("/profile/<int:pid>")
def profile(pid):
    db = get_db()
    p = get_player(db, pid)
    rounds = model.load_rounds(db, team_id())
    data = profile_data(db, p, rounds, request.args.get("runde", type=int), show_all=request.args.get("alle") == "1")
    d = model.parse_date(p["birth_date"])
    return render_template("profile.html", p=p, age_note=model.age_note(model.quarter(d)) if d else "", photos=photo_ids(get_db()), **data)
