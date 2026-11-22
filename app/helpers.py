"""Små delte hjælpefunktioner til views."""
from flask import abort, g

from . import model
from .db import get_setting


def team_id():
    if not g.get("team"):
        abort(403)
    return g.team["id"]


def active_players(db, include_inactive=False):
    sql = "SELECT * FROM players WHERE team_id=?" + ("" if include_inactive else " AND active=1") + " ORDER BY name COLLATE NOCASE"  # nosec B608 – identifikatorer fra faste lister / kun ?-pladsholdere
    return db.execute(sql, (team_id(),)).fetchall()


def get_player(db, pid):
    """Henter en spiller – kun hvis den tilhører det aktive hold (ellers 404, så andre holds data ikke kan nås)."""
    row = db.execute("SELECT * FROM players WHERE id=? AND team_id=?", (pid, team_id())).fetchone()
    if not row:
        abort(404)
    return row


def photo_ids(db):
    """Id'er på det aktive holds spillere, der har et billede (til mini-visning)."""
    return {r[0] for r in db.execute("SELECT pp.player_id FROM player_photos pp JOIN players p ON p.id=pp.player_id WHERE p.team_id=?", (team_id(),))}


def positions_of(p):
    """Spillerens positionsvalg i præferencerækkefølge (op til 4)."""
    return [p[k] for k in model.POSITION_FIELDS if p[k]]


def neighbours(players, pid):
    """(forrige_id, næste_id) i den viste rækkefølge."""
    ids = [p["id"] for p in players]
    if pid not in ids:
        return None, None
    i = ids.index(pid)
    return (ids[i - 1] if i > 0 else None), (ids[i + 1] if i + 1 < len(ids) else None)


def int_in(value, lo, hi):
    try:
        v = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi else None


ROUND_OPEN_DAYS = 30            # en runde lukkes 30 dage efter første indtastning


def round_info(db):
    """Runderne med navn, dato og status: åbnet (første indtastning), lukkedato og om runden er lukket for indtastning."""
    from datetime import date, timedelta
    today = date.today()
    with_data = {r["round"] for r in db.execute("SELECT DISTINCT e.round FROM evaluations e JOIN players p ON p.id=e.player_id WHERE p.team_id=?", (team_id(),))}
    out = []
    for r in g.rounds:
        label = get_setting(db, team_id(), f"round_label_{r}") or f"Evaluering {r}"
        opened = get_setting(db, team_id(), f"round_opened_{r}")
        try:
            closes = date.fromisoformat(opened) + timedelta(days=ROUND_OPEN_DAYS) if opened else None
        except ValueError:
            closes = None
        out.append(dict(no=r, label=label, date=get_setting(db, team_id(), f"round_date_{r}"), opened=opened, closes=closes.isoformat() if closes else "",
                        closed=bool(closes and today > closes), has_data=r in with_data))
    return out


def round_window(infos):
    """De to seneste runder med data og den næste (første runde uden data efter dem). Resten vises kun, når man går ind på siden."""
    data = [i["no"] for i in infos if i["has_data"]]
    last2 = data[-2:]
    after = [i["no"] for i in infos if i["no"] > (data[-1] if data else 0) and not i["has_data"]]
    nxt = after[:1]
    return sorted(set(last2 + nxt))


def touch_round_opened(db, rnd):
    """Registrerer dagen for første indtastning i runden (starter de 30 dage)."""
    from datetime import date
    from .db import set_setting
    if not get_setting(db, team_id(), f"round_opened_{rnd}"):
        set_setting(db, team_id(), f"round_opened_{rnd}", date.today().isoformat())


def default_round(rounds, preferred=None):
    """Den nyeste runde med data – ellers 1."""
    if preferred in g.rounds:
        return preferred
    for r in reversed(g.rounds):
        if rounds.get(r):
            return r
    return 1


def valid_choice(value, choices):
    return value if value in choices else None
