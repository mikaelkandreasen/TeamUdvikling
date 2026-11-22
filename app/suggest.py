"""Opstillingsforslag: fordeler spillere på pladser pr. periode, så spilletid jævnes ud og hvide pletter (position en spiller aldrig har prøvet) udfyldes først.

Rene funktioner uden database. Pr. periode vælges først hvem der spiller (færrest minutter i kampen, derefter færrest i alt over tid),
og de valgte fordeles på pladserne med den billigste samlet tildeling (ungarsk metode): 0 minutter i positionsgruppen er langt billigst.
"""
WHITE_SPOT_BONUS = -100


def _assign(cost):
    """Mindste samlede pris for rækker ≤ kolonner (ungarsk metode, O(n²m)). Returnerer kolonne pr. række."""
    n, m = len(cost), len(cost[0]) if cost else 0
    inf = float("inf")
    u, v, p, way = [0] * (n + 1), [0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv, used = [inf] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], inf, 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    res = [0] * n
    for j in range(1, m + 1):
        if p[j]:
            res[p[j] - 1] = j - 1
    return res


def suggest(slots, group_of, player_ids, hist, periods, period_min, absent=(), use_gk=True):
    """slots: [{i, tag}], hist: {pid: {gruppe: minutter}} fra tidligere kampe.
    Returnerer (assign {(periode, plads): pid}, udfyldte hvide pletter [(pid, gruppe)])."""
    cols = [s for s in slots if use_gk or group_of(s["tag"]) != "GK"]
    pool = [p for p in player_ids if p not in set(absent)]
    cur_total = {p: 0 for p in pool}
    cur_grp = {p: {} for p in pool}
    hist_total = {p: sum((hist.get(p) or {}).values()) for p in pool}
    assign, filled = {}, []
    for per in range(periods):
        if not cols or not pool:
            break
        chosen = sorted(pool, key=lambda p: (cur_total[p], hist_total[p], p))[:len(cols)]
        cost = []
        for p in chosen:
            row = []
            for s in cols:
                k = group_of(s["tag"])
                mins = (hist.get(p) or {}).get(k, 0) + cur_grp[p].get(k, 0)
                row.append(WHITE_SPOT_BONUS if mins == 0 else mins)
            cost.append(row)
        for p, c in zip(chosen, _assign(cost)):
            s = cols[c]
            k = group_of(s["tag"])
            if (hist.get(p) or {}).get(k, 0) + cur_grp[p].get(k, 0) == 0:
                filled.append((p, k))
            cur_grp[p][k] = cur_grp[p].get(k, 0) + period_min
            cur_total[p] += period_min
            assign[(per, s["i"])] = p
    return assign, filled
