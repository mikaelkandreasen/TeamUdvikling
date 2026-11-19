"""Små delte hjælpefunktioner til views."""
from flask import abort, g

from . import model
from .db import get_setting


def team_id():
    if not g.get("team"):
        abort(403)
    return g.team["id"]


def active_players(db, include_inactive=False):
    sql = "SELECT * FROM players WHERE team_id=?" + ("" if include_inactive else " AND active=1") + " ORDER BY name COLLATE NOCASE"
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


def round_info(db):
    out = []
    for r in g.rounds:
        label = get_setting(db, team_id(), f"round_label_{r}") or f"Evaluering {r}"
        out.append(dict(no=r, label=label, date=get_setting(db, team_id(), f"round_date_{r}")))
    return out


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
