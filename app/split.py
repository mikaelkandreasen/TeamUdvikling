"""Deling af truppen i op til 9 hold (3 × A, 3 × B, 3 × C). Rene funktioner – ingen databaseadgang.

Regler (spillerniveau fra trænerens vurdering):
* A-holdene får A+, A og B (A+/A først, derefter bedste B), B-holdene får B (og evt. overskydende A+/A), C-holdene får resten (C, D, nystartede, uvurderede).
* Holdstørrelse = spillere på banen + udskiftere (fra holdprofilen). Hold fyldes i rækkefølge: A1, A2, A3, B1 … – mangler der spillere, fyldes A-holdene altså først.
* Inden for et hold er de bedste (efter samlet score) på banen, resten udskiftere.
"""
TIERS = ("A", "B", "C")
_RANK = {"A+": 0, "A": 1, "B": 2}


def _key(p):
    return (_RANK.get(p.get("level") or "", 3), -(p.get("score") or 0), (p.get("name") or "").lower(), p["id"])


def split(players, size, subs, per_tier=3):
    """players: [{id, name, level, score}]. Returnerer (teams, unplaced). teams: [{name, tier, no, players:[...], starters:int, short:int}]."""
    per_tier = max(1, min(3, int(per_tier)))
    cap = max(1, size + max(0, subs))
    top = sorted((p for p in players if p.get("level") in ("A+", "A")), key=_key)
    mid = sorted((p for p in players if p.get("level") == "B"), key=_key)
    low = sorted((p for p in players if p.get("level") not in ("A+", "A", "B")), key=lambda p: (-(p.get("score") or 0), (p.get("name") or "").lower(), p["id"]))
    a_pool = top + mid
    a_take, rest = a_pool[:per_tier * cap], a_pool[per_tier * cap:]          # A-holdene fyldes først
    b_take, rest = rest[:per_tier * cap], rest[per_tier * cap:]
    c_take, left = (rest + low)[:per_tier * cap], (rest + low)[per_tier * cap:]
    teams = []
    for tier, group in zip(TIERS, (a_take, b_take, c_take)):
        for n in range(per_tier):
            members = sorted(group[n * cap:(n + 1) * cap], key=_key if tier != "C" else (lambda p: (-(p.get("score") or 0), (p.get("name") or "").lower(), p["id"])))
            teams.append(dict(name=f"{tier}-hold {n + 1}" if per_tier > 1 else f"{tier}-hold", tier=tier, no=n + 1, players=members,
                              starters=min(size, len(members)), short=max(0, size - len(members))))
    return teams, left
