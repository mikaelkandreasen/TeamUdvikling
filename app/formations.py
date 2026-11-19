"""Opstillinger (3v3, 5v5, 8v8, 11v11), pladser på banen og forslag til hold. Rene funktioner uden Flask/DB – testes i tests/test_formations.py.

En opstilling er en liste af linjer fra egen målmand og frem; hver linje er en liste af positioner fra venstre mod højre set fra holdets egen retning
(fremad). Koordinater er procent af banen (x: 0 = venstre, 100 = højre; y: 0 = modstanderens mål, 100 = eget mål).
"""
GK, DEF, RB, LB, CB = "Målmand", "Forsvar", "Højre back", "Venstre back", "Midtstopper"
DM, CM, AM = "Defensiv midtbane", "Midtbane", "Offensiv midtbane"
RW, LW, ST = "Højre kant", "Venstre kant", "Angreb"

GAME_TYPES = {"3v3": 3, "5v5": 5, "8v8": 8, "11v11": 11}          # antal spillere på banen
DEFAULT_TYPE = "8v8"                                                # U11 spiller typisk 8-mands

FORMATIONS = {
    "3v3": {                                                        # ingen målmand
        "1-2": [[DEF], [LW, RW]],
        "2-1": [[LB, RB], [ST]],
        "1-1-1": [[DEF], [CM], [ST]],
    },
    "5v5": {
        "1-2-1": [[GK], [CB], [CM, CM], [ST]],                      # diamant
        "2-2": [[GK], [LB, RB], [ST, ST]],                          # firkant
        "2-1-1": [[GK], [LB, RB], [CM], [ST]],
        "1-1-2": [[GK], [DEF], [CM], [ST, ST]],
    },
    "8v8": {
        "3-3-1": [[GK], [LB, CB, RB], [LW, CM, RW], [ST]],
        "2-3-2": [[GK], [LB, RB], [LW, CM, RW], [ST, ST]],
        "3-2-2": [[GK], [LB, CB, RB], [CM, CM], [ST, ST]],
        "2-4-1": [[GK], [CB, CB], [LW, CM, CM, RW], [ST]],
    },
    "11v11": {
        "4-3-3": [[GK], [LB, CB, CB, RB], [CM, DM, CM], [LW, ST, RW]],
        "4-4-2": [[GK], [LB, CB, CB, RB], [LW, CM, CM, RW], [ST, ST]],
        "4-2-3-1": [[GK], [LB, CB, CB, RB], [DM, DM], [LW, AM, RW], [ST]],
        "3-5-2": [[GK], [CB, CB, CB], [LW, CM, DM, CM, RW], [ST, ST]],
        "3-4-3": [[GK], [CB, CB, CB], [LW, CM, CM, RW], [LW, ST, RW]],
    },
}
DEFAULT_FORMATION = {"3v3": "1-2", "5v5": "1-2-1", "8v8": "3-3-1", "11v11": "4-3-3"}


def is_valid(game_type, formation):
    return formation in FORMATIONS.get(game_type, {})


def slots(game_type, formation):
    """Pladserne i en opstilling: [{i, tag, line, x, y}] i fast rækkefølge (bagfra og fra venstre mod højre)."""
    lines = FORMATIONS[game_type][formation]
    out, n = [], len(lines)
    for li, line in enumerate(lines):
        y = 90 - li * (76 / (n - 1)) if n > 1 else 50
        m = len(line)
        margin = {1: 50, 2: 28, 3: 18}.get(m, 12)
        for j, tag in enumerate(line):
            x = 50 if m == 1 else margin + (100 - 2 * margin) * j / (m - 1)
            out.append(dict(i=len(out), tag=tag, line=li, x=round(x, 1), y=round(y, 1)))
    return out


# ---------------------------------------------------------------- hvor godt passer en spiller til en plads?
GROUP = {"Målmand": "GK", "Forsvar": "DEF", "Højre back": "DEF", "Venstre back": "DEF", "Midtstopper": "DEF",
         "Midtbane": "MID", "Defensiv midtbane": "MID", "Offensiv midtbane": "MID",
         "Kant": "WING", "Højre kant": "WING", "Venstre kant": "WING", "Angreb": "ATT", "Allround": "ALL"}
NEAR = {frozenset(x) for x in (("WING", "ATT"), ("WING", "MID"), ("MID", "ATT"), ("MID", "DEF"))}


def affinity(pos, tag):
    """0–100: hvor godt en position (spillerens valg) dækker pladsens position."""
    if not pos or not tag:
        return 0
    if pos == tag:
        return 100
    if pos == "Allround":
        return 5 if tag == GK else 55
    if tag == GK or pos == GK:
        return 0                                                    # målmand spiller kun målmand (og omvendt)
    gp, gt = GROUP[pos], GROUP[tag]
    if gp == "WING" and gt == "WING":
        return 90 if pos == "Kant" or tag == "Kant" else 60         # «Kant» passer begge sider; forkert side er 2. bedste
    if gp == gt:
        if tag == DEF or tag == CM:                                 # generel «Forsvar»/«Midtbane»-plads tager alle i gruppen
            return 85
        if pos == DEF or pos == CM:
            return 80
        return 60
    return 40 if frozenset((gp, gt)) in NEAR else 0


def fit(positions, tag):
    """Bedste match blandt spillerens (op til 4) positionsvalg; senere valg trækker 6 point pr. trin."""
    best = 0
    for k, pos in enumerate([p for p in positions if p][:4]):
        best = max(best, affinity(pos, tag) - 6 * k)
    return max(0, best)


def choice_no(positions, tag):
    """Hvilket valg (1–4) matcher pladsen præcist? None hvis intet."""
    for k, pos in enumerate([p for p in positions if p][:4], start=1):
        if pos == tag:
            return k
    return None


# ---------------------------------------------------------------- forslag: optimal fordeling (ungarsk metode)
def _hungarian(cost):
    """Minimér samlet omkostning. cost: n rækker × m kolonner, n <= m. Returnerer kolonne pr. række."""
    n, m = len(cost), len(cost[0])
    INF = float("inf")
    u, v, p, way = [0.0] * (n + 1), [0.0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv, used = [INF] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], INF, 0
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
    ans = [0] * n
    for j in range(1, m + 1):
        if p[j]:
            ans[p[j] - 1] = j - 1
    return ans


def best_assignment(value):
    """value[r][c] = point for at sætte kolonne c på række r. Maksimerer summen. Returnerer {række: kolonne} (så mange som muligt)."""
    rows, cols = len(value), len(value[0]) if value else 0
    if not rows or not cols:
        return {}
    top = max(max(r) for r in value)
    if rows <= cols:
        cost = [[top - x for x in r] for r in value]
        return {r: c for r, c in enumerate(_hungarian(cost))}
    cost = [[top - value[r][c] for r in range(rows)] for c in range(cols)]       # transponeret: kolonner bliver rækker
    return {r: c for c, r in enumerate(_hungarian(cost))}


def suggest(slot_list, players, scores=None, weight=10):
    """Foreslå hold. players: [{id, positions:[…]}]; scores: {id: samlet} (valgfri, vægt pr. scorepoint).
    Returnerer {plads_index: spiller_id}. Ved færre spillere end pladser står de sidste pladser tomme."""
    if not slot_list or not players:
        return {}
    players = sorted(players, key=lambda p: p["id"])
    value = [[fit(p["positions"], s["tag"]) + weight * ((scores or {}).get(p["id"]) or 0) for p in players] for s in slot_list]
    return {r: players[c]["id"] for r, c in best_assignment(value).items()}
