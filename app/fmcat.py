"""Holdets egne opstillinger (tabellen team_formations) gjort tilgængelige for formations.catalog() i den aktuelle forespørgsel."""
import json

from flask import g, has_request_context

from . import formations


def load():
    if not has_request_context() or not g.get("team"):
        return {}
    cached = g.get("_fmcat")
    if cached is not None:
        return cached
    from .db import get_db
    out = {}
    for r in get_db().execute("SELECT game_type, name, lines FROM team_formations WHERE team_id=? ORDER BY name COLLATE NOCASE", (g.team["id"],)):
        try:
            out.setdefault(r["game_type"], {})[r["name"]] = json.loads(r["lines"])
        except ValueError:
            continue
    g._fmcat = out
    return out


def reset():
    g._fmcat = None


def init_app(app):
    formations._loader = load
