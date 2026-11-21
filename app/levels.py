"""Beregnet spillerniveau: trænernes samlede niveauvurdering (1-5) fordelt 25 % A / 50 % B / 25 % C."""
from . import model


def calc(db, players, rounds):
    """players: aktive spillere på holdet. Returnerer {pid: dict(level, score, n, source)}.
    Score = gennemsnit af trænernes niveauvurdering i spillerens seneste runde med vurdering; uden vurdering bruges samlet score fra evalueringen."""
    ids = [p["id"] for p in players]
    ratings = {}
    for r in db.execute("SELECT round, player_id, score FROM level_ratings WHERE player_id IN (SELECT id FROM players WHERE team_id=?)",
                        (players[0]["team_id"],)) if players else []:
        ratings.setdefault(r["player_id"], {}).setdefault(r["round"], []).append(r["score"])
    info = {}
    for pid in ids:
        by_round = ratings.get(pid)
        if by_round:
            rnd = max(by_round)
            info[pid] = dict(score=model.mean(by_round[rnd]), n=len(by_round[rnd]), source="vurdering")
            continue
        _, res = model.latest(rounds, pid)
        if res and res["samlet"] is not None:
            info[pid] = dict(score=res["samlet"], n=0, source="samlet")
    dist = model.distribute_levels({pid: v["score"] for pid, v in info.items()})
    return {pid: dict(v, level=dist[pid]) for pid, v in info.items() if pid in dist}
