"""Rollebaseret navigation: hver rolle ser kun det, der er relevant for den.

* sysadmin  – systemadministrator: Administration, Beskeder, Min konto (holdsider kun når et hold er åbnet).
* clubadmin – klubadministrator: Klubadministration, Beskeder, Min konto (holdsider kun når et hold er åbnet).
* head      – chef-træner: som træner + «Mit hold» og «Assistenter» (invitation).
* trainer   – træner: holdets sider.
* assistant – assistent (læseadgang): kan se og evaluere – uden kampe, holdsætning, motivation, udviklingsdata og rapporter.

Menuen er kun bekvemmelighed – adgang afgøres stadig af rolle-tjek på de enkelte sider.
"""
from flask import g, request

from . import scope

# (endpoint, tekst, funktion der skal være slået til)
COACH = [("main.home", "Hjem", ""), ("players.index", "Spillere", ""), ("evaluation.eval_home", "Evaluering", ""), ("evaluation.team", "Teamoversigt", ""),
         ("evaluation.development", "Udvikling", ""), ("evaluation.position_view", "Position & bane", ""), ("lineup.index", "Holdsætning", "lineup"),
         ("matches.index", "Kampe", "matches"), ("evaluation.areas", "Områder", ""), ("motivation.matrix", "Motivation", "motivation"),
         ("devdata.matrix", "Udviklingsdata", "devdata"), ("reports.index", "Rapporter", ""), ("main.criteria", "Skala & kriterier", "")]
ASSISTANT_HIDDEN = {"lineup.index", "matches.index", "motivation.matrix", "devdata.matrix", "reports.index"}
TEAM_BLUEPRINTS = {"players", "evaluation", "motivation", "devdata", "lineup", "team", "matches", "conv", "reports"}
LOCKED_FOR_ASSISTANTS = {"lineup", "matches", "motivation", "devdata", "reports"}   # blueprints: låst på serveren (B-051)
TEAM_ENDPOINTS = {"main.home", "main.mobile", "main.criteria"}


def kind(db, user, team):
    if not user:
        return None
    if scope.is_sysadmin(user):
        return "sysadmin"
    if scope.is_clubadmin(user):
        return "clubadmin"
    if user["readonly"]:
        return "assistant"
    if team and team["id"] in scope.head_team_ids(db, user):
        return "head"
    return "trainer"


def on_team_page(ep):
    return ep in TEAM_ENDPOINTS or ep.split(".")[0] in TEAM_BLUEPRINTS


def hidden(k):
    return ASSISTANT_HIDDEN if k == "assistant" else set()


def menu(k, ep, features, team):
    """Liste af {ep,label,on} og {sep:…}-skillelinjer til sidemenuen."""
    out = []
    manager = k in ("sysadmin", "clubadmin")
    adm_on = ep.startswith(("admin.", "invites_admin."))
    if manager:
        out.append(dict(ep="admin.index", label="Administration" if k == "sysadmin" else "Klubadministration", on=adm_on))
        if team and not on_team_page(ep):
            out.append(dict(ep="main.home", label="Åbn holdet: " + team["name"], on=False, args={"hold": 1}))
        if team and on_team_page(ep):
            out.append(dict(sep=team["name"]))
    if not manager or on_team_page(ep):
        skip = hidden(k)
        for e, label, f in COACH:
            if e in skip or (f and not features.get(f, True)):
                continue
            out.append(dict(ep=e, label=label, on=ep == e, args={"hold": 1} if manager and e == "main.home" else {}))
        if k in ("head", "clubadmin", "sysadmin") and team:
            out.append(dict(ep="team.index", label="Mit hold" if k == "head" else "Holdets side", on=ep.startswith("team.")))
    elif k == "head":
        pass
    if k == "head":
        out.append(dict(ep="invites_admin.index", label="Assistenter", on=ep.startswith("invites_admin.")))
    out.append(dict(ep="inbox.index", label="Beskeder", on=ep == "inbox.index"))
    out.append(dict(ep="auth.account", label="Min konto", on=ep == "auth.account"))
    return out


def tabs(k, ep, team):
    """Faner i mobilens bundmenu: (endpoint, ikon, tekst, aktiv)."""
    if k in ("sysadmin", "clubadmin"):
        return [("admin.index", "🏛", "Administration" if k == "sysadmin" else "Klub", ep.startswith(("admin.", "invites_admin."))),
                ("inbox.index", "✉", "Beskeder", ep == "inbox.index"),
                ("main.menu", "☰", "Mere", ep == "main.menu")]
    t = [("main.mobile", "🏠", "Hjem", ep in ("main.mobile", "main.home")), ("players.index", "👧", "Spillere", ep.startswith("players.")),
         ("evaluation.eval_home", "✅", "Evaluér", ep.startswith("evaluation.eval"))]
    if k != "assistant":
        t.append(("reports.index", "📄", "Rapport", ep.startswith("reports.")))
    t.append(("main.menu", "☰", "Mere", ep == "main.menu"))
    return t


def context(db):
    """Skabelonvariable; kaldes fra context processor."""
    from . import features as feat
    user, team = g.get("user"), g.get("team")
    k = kind(db, user, team) if user else None
    ep = request.endpoint or ""
    return dict(nav_kind=k, nav_hidden=hidden(k),
                nav_items=(lambda: menu(k, ep, feat.current(), team)) if k else (lambda: []),
                nav_tabs=(lambda: tabs(k, ep, team)) if k else (lambda: []))
