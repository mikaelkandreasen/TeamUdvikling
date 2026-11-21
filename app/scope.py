"""Roller og afgrænsning.

* `admin`      = systemadministrator: alt, på tværs af alle klubber (opretter klubber og klubadministratorer).
* `clubadmin`  = klubadministrator: administrerer sin egen klub (profil, hold, trænere, invitationer) – intet andet.
* `trainer`    = træner: kun de hold, vedkommende er tilknyttet (alle i samme klub).
Alt der rører andre klubbes data svarer 404 (ikke 403), så eksistensen ikke afsløres.
"""

ROLES = ("trainer", "clubadmin", "admin")
ROLE_LABEL = {"admin": "Systemadministrator", "clubadmin": "Klubadministrator", "trainer": "Træner"}


def is_sysadmin(user):
    return bool(user) and user["role"] == "admin"


def is_clubadmin(user):
    return bool(user) and user["role"] == "clubadmin"


def is_manager(user):
    return is_sysadmin(user) or is_clubadmin(user)


def my_club(user):
    """Klub-id som en klubadministrator må administrere; None for systemadministratorer (= alle)."""
    return None if is_sysadmin(user) else user["club_id"]


def can_manage_club(user, club_id):
    return is_sysadmin(user) or (is_clubadmin(user) and club_id is not None and user["club_id"] == club_id)


def can_manage_team(db, user, team_id):
    row = db.execute("SELECT club_id FROM teams WHERE id=?", (team_id,)).fetchone()
    return bool(row) and can_manage_club(user, row["club_id"])


def can_manage_user(user, target):
    """Systemadministratorer styrer alle. Klubadministratorer styrer kun *trænere* i egen klub (roller styres af systemadministratorer)."""
    if is_sysadmin(user):
        return True
    return is_clubadmin(user) and target["role"] == "trainer" and target["club_id"] == user["club_id"]
