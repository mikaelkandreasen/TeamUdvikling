"""Funktioner der kan slås til/fra pr. hold (indstilles af chef-træner, klubadministrator eller systemadministrator).

Slået-fra funktioner skjules i menuer og svarer 404. Eksisterende hold beholder alt, undtagen mascot (slået fra fra start).
"""
from flask import abort, g, request

from .db import get_setting

FEATURES = (
    ("devdata", "Udviklingsdata: fremmøde, kampdeltagelse, trivsel, motorik og handleplan", True),
    ("motivation", "Motivation og træningsønsker", True),
    ("lineup", "Holdsætning (opstillinger og deling i A/B/C-hold)", True),
    ("levels", "Spillerniveau (A, B, C, D efter DBU)", True),
    ("notes", "Holdnoter", True),
    ("mascot", "Mascot (hvem har den med hjem)", False),
)
KEYS = [k for k, _l, _d in FEATURES]
BLUEPRINT = {"devdata": "devdata", "motivation": "motivation", "lineup": "lineup"}
ENDPOINT = {"team.notes": "notes", "team.notes_add": "notes", "team.notes_delete": "notes", "team.levels": "levels",
            "team.mascot": "mascot", "team.mascot_return": "mascot", "team.mascot_delete": "mascot", "team.mascot_report": "mascot"}


def load(db, team_id):
    return {k: (get_setting(db, team_id, f"feat_{k}") or ("1" if d else "0")) == "1" for k, _l, d in FEATURES}


def current():
    """Funktioner for det aktive hold (cachet pr. request). Uden hold: alt slået til."""
    if "features" not in g:
        from .db import get_db
        g.features = load(get_db(), g.team["id"]) if g.get("team") else {k: True for k in KEYS}
    return g.features


def guard():
    """before_request: 404 hvis siden hører til en slået-fra funktion."""
    ep = request.endpoint or ""
    key = ENDPOINT.get(ep) or BLUEPRINT.get(ep.split(".")[0])
    if key and g.get("user") and not current().get(key, True):
        abort(404)
