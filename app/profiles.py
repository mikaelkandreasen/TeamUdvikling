"""Flere profiler pr. bruger: en bruger har sin hovedprofil (users.role/club_id) og kan af en systemadministrator få ekstra profiler
(fx træner i én klub og klubadministrator i en anden). Efter login vælger brugeren hvilken profil der er aktiv; al adgang følger den aktive profil."""
from flask import g, session

from . import scope


def list_for(db, user):
    """Alle profiler for brugeren; hovedprofilen først (id 0)."""
    out = [dict(id=0, role=user["role"], club_id=user["club_id"], main=True)]
    out += [dict(r, main=False) for r in db.execute("SELECT id, role, club_id FROM user_profiles WHERE user_id=? ORDER BY id", (user["id"],))]
    names = {r["id"]: r["name"] for r in db.execute("SELECT id, name FROM clubs")}
    for p in out:
        p["club_name"] = names.get(p["club_id"]) or ""
        p["label"] = scope.ROLE_LABEL.get(p["role"], p["role"]) + (f" – {p['club_name']}" if p["club_name"] and p["role"] != "admin" else "")
    return out


def apply(db, row):
    """Returnerer brugerrækken med den aktive profils rolle og klub. Ugyldigt/fjernet valg falder tilbage til hovedprofilen."""
    pid = session.get("profile")
    if not pid:
        return row
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        session.pop("profile", None)
        return row
    prof = db.execute("SELECT * FROM user_profiles WHERE id=? AND user_id=?", (pid, row["id"])).fetchone()
    if not prof:
        session.pop("profile", None)
        return row
    d = dict(row)
    d.update(role=prof["role"], club_id=prof["club_id"], profile_id=prof["id"])
    if prof["role"] != "trainer":
        d["readonly"] = 0
    return d


def switch(db, user_row, pid):
    """Vælg aktiv profil (0 = hovedprofil). True hvis profilen tilhører brugeren."""
    if not pid:
        session.pop("profile", None)
        return True
    if db.execute("SELECT 1 FROM user_profiles WHERE id=? AND user_id=?", (pid, user_row["id"])).fetchone():
        session["profile"] = pid
        session.pop("view_as", None)
        return True
    return False
