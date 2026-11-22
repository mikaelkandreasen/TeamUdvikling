"""Evalueringskriterier pr. hold: standardsættet kommer fra `model.CRITERIA`; holdets egne tekster ligger i tabellen `team_criteria`.

Alle læsninger af kriterier for et hold går via `for_team()`. Struktur (4 roller × 6 nøglefærdigheder) er stadig fast i `model.py`;
tabellen er første skridt mod hold med egne roller og færdigheder (B-042b).
"""
from . import model

MAX_TEXT = 300


def custom_texts(db, tid):
    return {r["idx"]: r["description"] for r in db.execute("SELECT idx, description FROM team_criteria WHERE team_id=?", (tid,))}


def for_team(db, tid):
    """De 24 kriterier med holdets egne beskrivelser (standardtekst hvor intet er overskrevet)."""
    custom = custom_texts(db, tid)
    out = []
    for c in model.CRITERIA:
        text = (custom.get(c["idx"]) or "").strip()
        out.append(dict(c, desc=text or c["desc"], custom=bool(text)))
    return out


def save_texts(db, tid, texts):
    """texts: {idx: tekst}. Tekster der er tomme eller lig standarden fjernes (så standarden kan ændres senere). Returnerer antal ændrede."""
    before = custom_texts(db, tid)
    changed = 0
    for c in model.CRITERIA:
        v = (texts.get(c["idx"]) or "").strip()[:MAX_TEXT]
        if v == c["desc"]:
            v = ""
        if v != (before.get(c["idx"]) or ""):
            changed += 1
        if v:
            db.execute("INSERT INTO team_criteria(team_id,idx,description) VALUES(?,?,?) ON CONFLICT(team_id,idx) DO UPDATE SET description=excluded.description", (tid, c["idx"], v))
        else:
            db.execute("DELETE FROM team_criteria WHERE team_id=? AND idx=?", (tid, c["idx"]))
    return changed
