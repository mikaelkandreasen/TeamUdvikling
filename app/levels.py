"""Beregnet spillerniveau: trænernes niveauvurdering fordeles automatisk (som standard 25 % A / 50 % B / 25 % C)."""
from . import model
from .db import get_setting


def shares(db, tid):
    """(andel A, andel C) i procent for holdet – justeres under holdindstillinger."""
    out = []
    for key, default in (("level_share_a", model.DEFAULT_SHARES[0]), ("level_share_c", model.DEFAULT_SHARES[1])):
        try:
            v = int(get_setting(db, tid, key))
        except (TypeError, ValueError):
            v = default
        out.append(min(45, max(0, v)))
    return tuple(out)


def calc(db, players, rounds):
    """players: aktive spillere på holdet. Returnerer {pid: dict(level, score, n, source)}.
    Score = gennemsnit af trænernes niveau (valgt i dropdown, ellers udledt af de DBU-valg pr. kompetence) i spillerens seneste runde med vurdering; uden vurdering bruges samlet score
    fra de 24 kriterier (1-5) omregnet til samme skala. Beregnes løbende – der er ikke noget at trykke på."""
    if not players:
        return {}
    tid = players[0]["team_id"]
    # pr. spiller, runde og træner: valgt niveau (dropdown) eller – hvis intet er valgt – niveauet fra DBU-valg
    sel, ticks = {}, {}
    for r in db.execute("SELECT round, player_id, trainer_id, level FROM level_ratings WHERE player_id IN (SELECT id FROM players WHERE team_id=?)", (tid,)):
        if r["level"] in model.LEVEL_ORD:
            sel[(r["player_id"], r["round"], r["trainer_id"])] = r["level"]
    for r in db.execute("SELECT round, player_id, trainer_id, item FROM dbu_checks WHERE player_id IN (SELECT id FROM players WHERE team_id=?)", (tid,)):
        ticks.setdefault((r["player_id"], r["round"], r["trainer_id"]), set()).add(r["item"])
    per_player = {}
    for key in set(sel) | set(ticks):
        pid, rnd, trainer = key
        res = model.dbu_result(ticks.get(key, ()))
        if key in sel:
            score = float(model.LEVEL_ORD[sel[key]])
        elif res:
            score = model.LEVEL_ORD[res["level"]] + res["points"] / 100.0          # ranger spillere med samme niveau efter antal/vægt af udsagn
        else:
            continue
        per_player.setdefault(pid, {}).setdefault(rnd, []).append(score)
    info = {}
    for p in players:
        pid = p["id"]
        by_round = per_player.get(pid)
        if by_round:
            rnd = max(by_round)
            info[pid] = dict(score=model.mean(by_round[rnd]), n=len(by_round[rnd]), source="vurdering")
            continue
        _, res = model.latest(rounds, pid)
        if res and res["samlet"] is not None:
            info[pid] = dict(score=1 + (res["samlet"] - 1) * 5 / 4, n=0, source="samlet")          # 1-5 → 1-6
    a, c = shares(db, tid)
    dist = model.distribute_levels({pid: v["score"] for pid, v in info.items()}, a, c)
    return {pid: dict(v, level=dist[pid]) for pid, v in info.items() if pid in dist}
