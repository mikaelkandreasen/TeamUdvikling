"""Hold: hvilke hold en bruger har adgang til, og hvilket hold der er aktivt i sessionen.

Regler: administratorer har adgang til alle hold. Trænere har kun adgang til hold, de er tildelt i user_teams.
Alle data (spillere, evalueringer, motivation, udviklingsdata, indstillinger) hænger på et hold.
"""
from flask import g, session

from . import model
from .db import get_setting


def accessible_teams(db, user):
    if user["role"] == "admin":
        return db.execute("SELECT * FROM teams ORDER BY name COLLATE NOCASE").fetchall()
    if user["role"] == "clubadmin":
        return db.execute("SELECT * FROM teams WHERE club_id=? ORDER BY name COLLATE NOCASE", (user["club_id"],)).fetchall()
    return db.execute("SELECT t.* FROM teams t JOIN user_teams ut ON ut.team_id=t.id WHERE ut.user_id=? AND t.club_id IS ? "
                      "ORDER BY t.name COLLATE NOCASE", (user["id"], user["club_id"])).fetchall()


GUARDED = {"players", "evaluation", "motivation", "devdata", "lineup", "team", "matches", "conv"}


def archived_write_blocked(endpoint, method):
    """Arkiverede hold er skrivebeskyttede: ingen ændringer af spillere, evalueringer, data eller indstillinger."""
    if method in ("GET", "HEAD", "OPTIONS") or not g.get("team") or not g.team["archived"]:
        return False
    if endpoint in ("team.season",):
        return False
    return (endpoint or "").split(".")[0] in GUARDED or endpoint in ("admin.evaluations", "admin.settings")


def team_rounds(db, team_id):
    """Evalueringsrunder for et hold (standard 4, 2–8)."""
    try:
        n = int(get_setting(db, team_id, "rounds_n") or model.DEFAULT_ROUNDS)
    except ValueError:
        n = model.DEFAULT_ROUNDS
    return tuple(range(1, max(2, min(model.MAX_ROUNDS, n)) + 1))


def resolve(db, user):
    """Sætter g.teams (adgangsliste) og g.team (aktivt hold, altid valideret mod adgangslisten)."""
    g.teams = accessible_teams(db, user) if user else []
    g.team = None
    g.rounds = tuple(range(1, model.DEFAULT_ROUNDS + 1))
    if not g.teams:
        session.pop("team_id", None)
        return
    chosen = (next((t for t in g.teams if t["id"] == session.get("team_id")), None)
              or next((t for t in g.teams if not t["archived"]), None) or g.teams[0])
    g.team = chosen
    g.rounds = team_rounds(db, chosen["id"])
    session["team_id"] = chosen["id"]


def switch(db, user, team_id):
    """Skifter aktivt hold hvis brugeren har adgang. Returnerer True ved succes."""
    if any(t["id"] == team_id for t in accessible_teams(db, user)):
        session["team_id"] = team_id
        return True
    return False
