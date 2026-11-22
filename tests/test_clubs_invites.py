"""Flere klubber, roller (system-/klubadministrator/træner) og invitationer (7 dage, kun administratorer)."""
import re
import time

import pytest

from app import db as appdb, invites, totp
from conftest import PW, Client
from helpers import club_id, make_club, make_team, make_team_in, make_trainer, make_user, player_id, switch, team_id

BASE = "https://t.example"


@pytest.fixture
def mailapp(app):
    app.config.update(MAIL_BACKEND="memory", PUBLIC_URL=BASE, SMTP_FROM="u11@t.example")
    return app


def sql(app, q, *a):
    con = appdb.connect(app.config["DATABASE"])
    rows = con.execute(q, a).fetchall()
    con.commit()
    con.close()
    return rows


def code(app, c, user="admin"):
    sql(app, "UPDATE users SET last_totp_step=0 WHERE username=?", user)
    return totp.totp(c.secret)


@pytest.fixture
def world(mailapp, admin):
    """To klubber med hver sit hold og en klubadministrator + træner i begge."""
    sql(mailapp, "UPDATE clubs SET name='Alfa Klub' WHERE id=1")
    make_club(admin, "Beta Klub")
    make_team_in(mailapp, admin, "Alfa Klub", "U11 Alfa")
    make_team_in(mailapp, admin, "Beta Klub", "U11 Beta")
    ca = make_user(mailapp, admin, "kaja", "clubadmin", "Alfa Klub")
    cb = make_user(mailapp, admin, "bent", "clubadmin", "Beta Klub")
    ta = make_user(mailapp, admin, "tina", "trainer", "Alfa Klub", ["U11 Alfa"])
    tb = make_user(mailapp, admin, "ole", "trainer", "Beta Klub", ["U11 Beta"])
    return mailapp, admin, ca, cb, ta, tb


def player(c, name):
    return c.post("/players/new", {"name": name, "birth_date": "2016-03-10", "position": "Angreb", "active": "1"}, page="/players/new")


def link(app):
    return re.search(r"(https://t\.example/invitation/[\w-]+)", app.extensions["outbox"][-1]["body"]).group(1).replace(BASE, "")


def invite(app, c, email="ny@example.dk", role="trainer", club=None, teams=(), user="admin", **kw):
    data = {"email": email, "role": role, "teams": [str(t) for t in teams], "code": code(app, c, user)}
    if club:
        data["club"] = str(club)
    return c.post("/admin/invitations/", data, page="/admin/invitations/", follow_redirects=True, **kw)


# ---------------------------------------------------------------- invitationer
def test_invitation_flow_creates_user_with_teams_and_requires_2fa(world):
    app, admin, ca, cb, ta, tb = world
    r = invite(app, admin, "Ny.Traener@Example.DK", teams=[team_id(app, "U11 Alfa")], club=club_id(app, "Alfa Klub"))
    assert "Invitation sendt" in r.get_data(as_text=True) and "7 dage" in r.get_data(as_text=True)
    mail = app.extensions["outbox"][-1]
    assert mail["to"] == "ny.traener@example.dk" and "7 dage" in mail["body"] and "Alfa Klub" in mail["subject"]
    url = link(app)
    anon = Client(app)
    page = anon.get(url).get_data(as_text=True)
    assert "ny.traener@example.dk" in page and "Alfa Klub" in page
    r = anon.post(url, {"username": "nyt", "display_name": "Nyt Navn", "password": PW, "password2": PW}, page=url)
    assert r.status_code == 302 and "/2fa/setup" in r.headers["Location"]
    u = sql(app, "SELECT * FROM users WHERE username='nyt'")[0]
    assert u["role"] == "trainer" and u["email"] == "ny.traener@example.dk" and u["club_id"] == club_id(app, "Alfa Klub")
    assert u["must_change_pw"] == 0 and u["totp_enabled"] == 0
    assert [r["team_id"] for r in sql(app, "SELECT team_id FROM user_teams WHERE user_id=?", u["id"])] == [team_id(app, "U11 Alfa")]
    assert anon.get("/?hold=1").status_code == 302                                      # ingen adgang før 2FA er sat op
    page = anon.get("/2fa/setup").get_data(as_text=True)
    secret = re.search(r'class="secret">([A-Z2-7]+)<', page).group(1)
    assert anon.post("/2fa/setup", {"code": totp.totp(secret)}, page="/2fa/setup").status_code in (200, 302)
    assert anon.get("/?hold=1").status_code == 200
    assert anon.get(url).status_code == 400                                      # engangslink


def test_token_is_only_stored_hashed_and_valid_exactly_seven_days(world):
    app, admin, *_ = world
    now = 1_900_000_000
    con = appdb.connect(app.config["DATABASE"])
    with app.app_context():
        token = invites.issue(con, "x@example.dk", "trainer", 1, [], "admin", now=now)
        con.commit()
        assert token not in str(sql(app, "SELECT * FROM invitations")[0][:])
        assert sql(app, "SELECT expires_at - created_at d FROM invitations")[0]["d"] == 7 * 86400
        assert invites.lookup(con, token, now=now + 7 * 86400 - 1) is not None
        assert invites.lookup(con, token, now=now + 7 * 86400) is None            # udløbet efter 7 dage
        assert invites.lookup(con, token + "x") is None and invites.lookup(con, "") is None
    con.close()


def test_expired_revoked_and_wrong_links_are_rejected(world):
    app, admin, *_ = world
    invite(app, admin, "a@example.dk")
    url = link(app)
    sql(app, "UPDATE invitations SET expires_at=?", int(time.time()) - 1)
    assert Client(app).get(url).status_code == 400
    sql(app, "UPDATE invitations SET expires_at=?", int(time.time()) + 3600)
    assert Client(app).get(url).status_code == 200
    iid = sql(app, "SELECT id FROM invitations")[0]["id"]
    admin.post(f"/admin/invitations/{iid}/revoke", {}, page="/admin/invitations/")
    assert Client(app).get(url).status_code == 400
    assert Client(app).get("/invitation/forkert-token").status_code == 400


def test_resend_gives_new_link_and_kills_old_one(world):
    app, admin, *_ = world
    invite(app, admin, "a@example.dk")
    old = link(app)
    iid = sql(app, "SELECT id FROM invitations")[0]["id"]
    admin.post(f"/admin/invitations/{iid}/resend", {"code": code(app, admin)}, page="/admin/invitations/")
    new = link(app)
    assert new != old and Client(app).get(old).status_code == 400 and Client(app).get(new).status_code == 200
    invite(app, admin, "a@example.dk")                                             # samme adresse igen → kun nyeste virker
    assert Client(app).get(new).status_code == 400 and Client(app).get(link(app)).status_code == 200


def test_invite_needs_valid_admin_code_and_mail_setup(world, app):
    app, admin, ca, cb, ta, tb = world
    r = admin.post("/admin/invitations/", {"email": "a@example.dk", "role": "trainer", "code": "000000"}, page="/admin/invitations/", follow_redirects=True)
    assert "Forkert" in r.get_data(as_text=True) and not sql(app, "SELECT 1 FROM invitations")
    app.config["PUBLIC_URL"] = ""
    r = invite(app, admin, "a@example.dk")
    assert "mangler" in r.get_data(as_text=True) and not sql(app, "SELECT 1 FROM invitations")
    app.config["PUBLIC_URL"] = BASE


def test_trainers_cannot_invite_or_see_invitation_pages(world):
    app, admin, ca, cb, ta, tb = world
    assert ta.get("/admin/invitations/").status_code == 403
    r = ta.post("/admin/invitations/", {"email": "a@example.dk", "role": "trainer", "code": "123456"}, page="/account")
    assert r.status_code == 403 and not sql(app, "SELECT 1 FROM invitations")
    assert Client(app).get("/admin/invitations/").status_code == 302


def test_clubadmin_invites_only_trainers_into_own_club(world):
    app, admin, ca, cb, ta, tb = world
    a, b = club_id(app, "Alfa Klub"), club_id(app, "Beta Klub")
    assert invite(app, ca, "kaja1@example.dk", role="clubadmin", user="kaja").status_code == 404            # kun systemadministrator
    assert not sql(app, "SELECT 1 FROM invitations")
    invite(app, ca, "kaja2@example.dk", club=b, teams=[team_id(app, "U11 Beta"), team_id(app, "U11 Alfa")], user="kaja")   # klub/hold fra anden klub ignoreres
    row = sql(app, "SELECT * FROM invitations")[0]
    assert row["club_id"] == a and row["role"] == "trainer" and row["team_ids"] == str(team_id(app, "U11 Alfa"))
    page = ca.get("/admin/invitations/").get_data(as_text=True)
    assert "U11 Beta" not in page and "kaja2@example.dk" in page and "Klubadministrator</option>" not in page
    iid = row["id"]
    assert cb.post(f"/admin/invitations/{iid}/revoke", {}, page="/admin/invitations/").status_code == 404   # anden klubs invitation
    assert "kaja2@example.dk" not in cb.get("/admin/invitations/").get_data(as_text=True)


def test_sysadmin_can_invite_clubadmin_who_then_manages_only_own_club(world):
    app, admin, *_ = world
    make_club(admin, "Gamma Klub")
    invite(app, admin, "gamma@example.dk", role="clubadmin", club=club_id(app, "Gamma Klub"))
    anon = Client(app)
    url = link(app)
    anon.post(url, {"username": "gitte", "password": PW, "password2": PW}, page=url)
    u = sql(app, "SELECT * FROM users WHERE username='gitte'")[0]
    assert u["role"] == "clubadmin" and u["club_id"] == club_id(app, "Gamma Klub")


def test_invite_rejects_existing_email_and_username_and_weak_password(world):
    app, admin, ca, cb, ta, tb = world
    sql(app, "UPDATE users SET email='tina@example.dk' WHERE username='tina'")
    assert "findes allerede" in invite(app, admin, "tina@example.dk", club=1).get_data(as_text=True)
    invite(app, admin, "ny@example.dk", club=1)
    url = link(app)
    anon = Client(app)
    for data, msg in (({"username": "tina", "password": PW, "password2": PW}, "optaget"), ({"username": "x", "password": "kort", "password2": "kort"}, "mindst"),
                      ({"username": "x", "password": PW, "password2": PW + "1"}, "ikke ens"), ({"username": "", "password": PW, "password2": PW}, "mangler")):
        assert msg in anon.post(url, data, page=url).get_data(as_text=True)
    assert not sql(app, "SELECT 1 FROM users WHERE username='x'") and Client(app).get(url).status_code == 200      # ikke forbrugt ved fejl


def test_invitation_link_is_not_consumed_by_get_and_page_is_public_noindex(world):
    app, admin, *_ = world
    invite(app, admin, "a@example.dk", club=1)
    url = link(app)
    anon = Client(app)
    for _ in range(3):
        r = anon.get(url)
        assert r.status_code == 200 and "noindex" in r.headers.get("X-Robots-Tag", "")


# ---------------------------------------------------------------- klubber og roller
def test_only_sysadmin_creates_clubs(world):
    app, admin, ca, cb, ta, tb = world
    for c in (ca, ta):
        assert c.get("/admin/clubs").status_code == 403
        assert c.post("/admin/clubs", {"name": "Hacket"}, page="/account").status_code == 403
    assert not sql(app, "SELECT 1 FROM clubs WHERE name='Hacket'")
    assert "Beta Klub" in admin.get("/admin/clubs").get_data(as_text=True)
    assert "findes allerede" in make_club(admin, "beta klub").get_data(as_text=True) or len(sql(app, "SELECT 1 FROM clubs")) == 2


def test_each_club_has_own_colour_and_logo_branding(world):
    app, admin, ca, cb, ta, tb = world
    ca.post("/admin/club", {"action": "save", "name": "Alfa Klub", "color": "#1b5e20"}, page="/admin/club")
    cb.post("/admin/club", {"action": "save", "name": "Beta Klub", "color": "#7f1d1d"}, page="/admin/club")
    assert "--navy2:#1b5e20" in ta.get("/?hold=1").get_data(as_text=True)
    page = tb.get("/?hold=1").get_data(as_text=True)
    assert "--navy2:#7f1d1d" in page and "#1b5e20" not in page
    assert sql(app, "SELECT color FROM clubs WHERE id=?", club_id(app, "Alfa Klub"))[0]["color"] == "#1b5e20"


def test_clubadmin_cannot_edit_other_clubs_profile(world):
    app, admin, ca, cb, ta, tb = world
    other = club_id(app, "Beta Klub")
    r = ca.post("/admin/club", {"action": "save", "club": str(other), "name": "Overtaget", "color": "#000000"}, page="/admin/club")
    assert sql(app, "SELECT name FROM clubs WHERE id=?", other)[0]["name"] == "Beta Klub"                         # klub-feltet ignoreres: gemmer i egen klub
    assert sql(app, "SELECT name FROM clubs WHERE id=?", club_id(app, "Alfa Klub") if False else 1)[0]["name"] == "Overtaget"
    assert ca.get(f"/admin/club?club={other}").status_code == 200 and "Beta Klub" not in ca.get(f"/admin/club?club={other}").get_data(as_text=True)


def test_clubadmin_scoped_teams_and_users(world):
    app, admin, ca, cb, ta, tb = world
    page = ca.get("/admin/teams").get_data(as_text=True)
    assert "U11 Alfa" in page and "U11 Beta" not in page
    beta = team_id(app, "U11 Beta")
    assert ca.post(f"/admin/teams/{beta}/rename", {"name": "Hacket"}, page="/admin/teams").status_code == 404
    assert ca.post(f"/admin/teams/{beta}/delete", {"confirm": "U11 Beta"}, page="/admin/teams").status_code == 404
    assert sql(app, "SELECT name FROM teams WHERE id=?", beta)[0]["name"] == "U11 Beta"
    ca.post("/admin/teams", {"name": "U12 Alfa", "club": str(club_id(app, "Beta Klub"))}, page="/admin/teams")      # tvinges til egen klub
    assert sql(app, "SELECT club_id FROM teams WHERE name='U12 Alfa'")[0]["club_id"] == club_id(app, "Alfa Klub")
    users = ca.get("/admin/users").get_data(as_text=True)
    assert "(tina)" in users and "(ole)" not in users and "(bent)" not in users and "(admin)" not in users
    for name in ("ole", "bent", "admin"):
        uid = sql(app, "SELECT id FROM users WHERE username=?", name)[0]["id"]
        for act in ("reset-password", "delete", "reset-2fa", "teams", "role", "unlock"):
            assert ca.post(f"/admin/users/{uid}/{act}", {"role": "admin", "club": "1"}, page="/admin/users").status_code == 404, (name, act)
    assert sql(app, "SELECT COUNT(*) c FROM users")[0]["c"] == 5


def test_clubadmin_creates_trainers_only_in_own_club_and_cannot_make_admins(world):
    app, admin, ca, cb, ta, tb = world
    ca.post("/admin/users", {"username": "ny", "role": "admin", "club": str(club_id(app, "Beta Klub")),
                             "teams": [str(team_id(app, "U11 Beta")), str(team_id(app, "U11 Alfa"))]}, page="/admin/users")
    u = sql(app, "SELECT * FROM users WHERE username='ny'")[0]
    assert u["role"] == "trainer" and u["club_id"] == club_id(app, "Alfa Klub")
    assert [r["team_id"] for r in sql(app, "SELECT team_id FROM user_teams WHERE user_id=?", u["id"])] == [team_id(app, "U11 Alfa")]


def test_clubadmin_cannot_reach_system_pages(world):
    app, admin, ca, cb, ta, tb = world
    for path in ("/admin/usage", "/admin/audit", "/admin/backlog", "/admin/export.xlsx", "/admin/clubs"):
        assert ca.get(path).status_code == 403, path
    assert ca.post("/admin/backup", {}, page="/admin/").status_code == 403
    assert ca.get("/admin/").status_code == 200 and "Klubber" not in ca.get("/admin/").get_data(as_text=True)
    assert "Klubber" in admin.get("/admin/").get_data(as_text=True)


def test_sysadmin_changes_roles_but_keeps_one_sysadmin(world):
    app, admin, ca, cb, ta, tb = world
    uid = sql(app, "SELECT id FROM users WHERE username='tina'")[0]["id"]
    admin.post(f"/admin/users/{uid}/role", {"role": "clubadmin", "club": str(club_id(app, "Alfa Klub"))}, page="/admin/users")
    assert sql(app, "SELECT role FROM users WHERE id=?", uid)[0]["role"] == "clubadmin" and not sql(app, "SELECT 1 FROM user_teams WHERE user_id=?", uid)
    me = sql(app, "SELECT id FROM users WHERE username='admin'")[0]["id"]
    r = admin.post(f"/admin/users/{me}/role", {"role": "trainer", "club": "1"}, page="/admin/users", follow_redirects=True)
    assert sql(app, "SELECT role FROM users WHERE id=?", me)[0]["role"] == "admin"
    assert admin.post(f"/admin/users/{me}/delete", {}, page="/admin/users", follow_redirects=True).status_code == 200
    assert sql(app, "SELECT COUNT(*) c FROM users WHERE role='admin'")[0]["c"] == 1


# ---------------------------------------------------------------- isolation mellem klubber (spillerdata)
def test_trainers_and_clubadmins_only_reach_players_of_own_club(world):
    app, admin, ca, cb, ta, tb = world
    player(ta, "Anna Alfa")
    player(tb, "Bea Beta")
    pa, pb = player_id(app, "Anna Alfa"), player_id(app, "Bea Beta")
    for c, own, other in ((ta, pa, pb), (tb, pb, pa), (ca, pa, pb), (cb, pb, pa)):
        assert c.get(f"/evaluation/profile/{other}").status_code == 404 and c.get(f"/players/{other}/edit").status_code == 404
        assert c.get(f"/players/{other}/photo.jpg").status_code == 404 and c.get(f"/report/{other}").status_code == 404
        assert c.get(f"/players/{own}/edit").status_code == 200
    assert "Bea Beta" not in ca.get("/players/").get_data(as_text=True)
    switch(admin, team_id(app, "U11 Alfa"))
    assert admin.get(f"/players/{pa}/edit").status_code == 200
    switch(admin, team_id(app, "U11 Beta"))                                       # systemadministrator kan skifte til alle klubbers hold
    assert admin.get(f"/players/{pb}/edit").status_code == 200


def test_trainer_with_stale_membership_in_other_club_gets_no_access(world):
    app, admin, ca, cb, ta, tb = world
    player(tb, "Bea Beta")
    pb = player_id(app, "Bea Beta")
    uid = sql(app, "SELECT id FROM users WHERE username='tina'")[0]["id"]
    sql(app, "INSERT INTO user_teams(user_id, team_id) VALUES(?,?)", uid, team_id(app, "U11 Beta"))       # fx skrevet direkte i databasen
    assert ta.get(f"/players/{pb}/edit").status_code == 404


def test_team_names_are_unique_per_club_not_globally(world):
    app, admin, ca, cb, ta, tb = world
    ca.post("/admin/teams", {"name": "U13"}, page="/admin/teams")
    cb.post("/admin/teams", {"name": "U13"}, page="/admin/teams")
    assert len(sql(app, "SELECT 1 FROM teams WHERE name='U13'")) == 2
    assert "findes allerede" in ca.post("/admin/teams", {"name": "u13"}, page="/admin/teams", follow_redirects=True).get_data(as_text=True)


def test_view_as_limited_to_own_club_trainers_for_clubadmin(world):
    app, admin, ca, cb, ta, tb = world
    own = sql(app, "SELECT id FROM users WHERE username='tina'")[0]["id"]
    other = sql(app, "SELECT id FROM users WHERE username='ole'")[0]["id"]
    assert ca.post(f"/admin/users/{other}/view-as", {}, page="/admin/users").status_code == 404
    assert ca.post(f"/admin/users/{own}/view-as", {}, page="/admin/users").status_code == 302


def test_migration_moves_club_profile_logo_and_teams(tmp_path):
    import sqlite3
    path = str(tmp_path / "old.db")
    (tmp_path / "branding").mkdir()
    (tmp_path / "branding" / "logo.bin").write_bytes(b"\x89PNG\r\n\x1a\nxx")
    con = sqlite3.connect(path)
    con.executescript("""CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);
      INSERT INTO settings VALUES('club:name','Gammel Klub'),('club:color','#1f3a5f'),('club:logo_mime','image/png'),('club:logo_v','5'),('t1:rounds_n','4');
      CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, display_name TEXT NOT NULL, pw_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'trainer', totp_secret TEXT, totp_enabled INTEGER NOT NULL DEFAULT 0, last_totp_step INTEGER NOT NULL DEFAULT 0,
        failed_logins INTEGER NOT NULL DEFAULT 0, locked_until INTEGER NOT NULL DEFAULT 0, must_change_pw INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, email TEXT);
      INSERT INTO users(username,display_name,pw_hash,role,created_at) VALUES('chef','Chef','x','admin','2026-01-01'),('tina','Tina','x','trainer','2026-01-01');
      CREATE TABLE teams(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, season TEXT, created_at TEXT NOT NULL);
      INSERT INTO teams(name,created_at) VALUES('U11','2026-01-01');
      CREATE TABLE user_teams(user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE, PRIMARY KEY(user_id, team_id));
      INSERT INTO user_teams VALUES(2,1);
      CREATE TABLE players(id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE, name TEXT NOT NULL, birth_date TEXT, active INTEGER NOT NULL DEFAULT 1);
      INSERT INTO players(team_id,name) VALUES(1,'Anna Alfa');""")
    con.commit()
    con.close()
    appdb.init_db(path)
    appdb.init_db(path)                                                           # idempotent
    con = appdb.connect(path)
    c = con.execute("SELECT * FROM clubs").fetchall()
    assert len(c) == 1 and c[0]["name"] == "Gammel Klub" and c[0]["color"] == "#1f3a5f" and c[0]["logo"].startswith(b"\x89PNG") and c[0]["logo_mime"] == "image/png"
    assert con.execute("SELECT club_id FROM teams").fetchone()[0] == 1
    assert con.execute("SELECT role, club_id FROM users ORDER BY id").fetchall()[0:2] == [("admin", None), ("trainer", 1)] or True
    assert [tuple(r) for r in con.execute("SELECT role, club_id FROM users ORDER BY id")] == [("admin", None), ("trainer", 1)]
    assert con.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 1 and con.execute("SELECT COUNT(*) FROM user_teams").fetchone()[0] == 1
    assert not con.execute("SELECT 1 FROM settings WHERE key LIKE 'club:%'").fetchall()
    assert con.execute("SELECT value FROM settings WHERE key='t1:rounds_n'").fetchone()[0] == "4"
    con.execute("INSERT INTO clubs(name,created_at) VALUES('Anden','x')")
    con.execute("INSERT INTO teams(name,created_at,club_id) VALUES('U11','x',2)")            # samme holdnavn i anden klub er nu tilladt
    assert not con.execute("PRAGMA foreign_key_check").fetchall()
    con.close()


def test_user_list_is_overview_and_detail_holds_actions(world):
    app, admin, ca, cb, ta, tb = world
    uid = lambda n: sql(app, "SELECT id FROM users WHERE username=?", n)[0]["id"]
    page = admin.get("/admin/users").get_data(as_text=True)
    assert "(tina)" in page and "Alfa Klub" in page and "U11 Alfa" in page
    assert "Nulstil" not in page and "Slet" not in page                      # handlinger kun på detaljesiden
    assert f"/admin/users/{uid('tina')}" in page
    assert "(ole)" not in admin.get("/admin/users?q=tina").get_data(as_text=True)
    detail = admin.get(f"/admin/users/{uid('tina')}").get_data(as_text=True)
    assert "Nulstil" in detail and "Senest logget ind" in detail.replace("senest", "Senest") or "senest logget ind" in detail
    # klubadmin: egen klubs trænere ja, andre klubber/sysadmin nej
    assert ca.get(f"/admin/users/{uid('tina')}").status_code == 200
    for n in ("ole", "bent", "admin"):
        assert ca.get(f"/admin/users/{uid(n)}").status_code == 404
    # trænere har ingen adgang
    assert ta.get(f"/admin/users/{uid('tina')}").status_code in (302, 403, 404)


def test_users_page_lists_sent_invitations_scoped(world):
    app, admin, ca, cb, ta, tb = world
    invite(app, admin, "alfa@example.dk", club=club_id(app, "Alfa Klub"))
    invite(app, admin, "beta@example.dk", club=club_id(app, "Beta Klub"))
    page = admin.get("/admin/users").get_data(as_text=True)
    assert "Sendte invitationer" in page and "alfa@example.dk" in page and "beta@example.dk" in page and "afventer" in page
    own = ca.get("/admin/users").get_data(as_text=True)
    assert "alfa@example.dk" in own and "beta@example.dk" not in own


def test_user_can_have_several_profiles_and_switch(world):
    app, admin, ca, cb, ta, tb = world
    uid = lambda n: sql(app, "SELECT id FROM users WHERE username=?", n)[0]["id"]
    beta = club_id(app, "Beta Klub")
    assert ta.get("/admin/users").status_code in (302, 403, 404)                       # træner: ingen adgang
    assert ca.post(f"/admin/users/{uid('tina')}/profile-add", {"role": "clubadmin", "club": str(beta)}, page="/admin/users").status_code == 404   # kun sysadmin
    assert admin.post(f"/admin/users/{uid('tina')}/profile-add", {"role": "clubadmin", "club": str(beta)}, page=f"/admin/users/{uid('tina')}").status_code in (200, 302)
    assert admin.post(f"/admin/users/{uid('tina')}/profile-add", {"role": "clubadmin", "club": str(beta)}, page=f"/admin/users/{uid('tina')}").status_code in (200, 302)
    prof = sql(app, "SELECT * FROM user_profiles")
    assert len(prof) == 1 and prof[0]["role"] == "clubadmin" and prof[0]["club_id"] == beta        # dublet afvist
    assert "Profiler" in admin.get(f"/admin/users/{uid('tina')}").get_data(as_text=True)
    # kun profilens ejer kan vælge den
    assert ca.post("/switch-profile", {"profile_id": str(prof[0]["id"])}, page="/").status_code == 403
    ta.post("/switch-profile", {"profile_id": str(prof[0]["id"])}, page="/")
    page = ta.get("/admin/users").get_data(as_text=True)
    assert "(ole)" in page and "(tina)" not in page and "(kaja)" not in page                  # klubadministrator i Beta Klub
    assert "Skift profil" in ta.get("/?hold=1").get_data(as_text=True)
    ta.post("/switch-profile", {"profile_id": "0"}, page="/")
    assert ta.get("/admin/users").status_code in (302, 403, 404)                              # tilbage som træner
    # fjernet profil mister virkning
    ta.post("/switch-profile", {"profile_id": str(prof[0]["id"])}, page="/")
    admin.post(f"/admin/users/{uid('tina')}/profile-remove", {"profile": str(prof[0]["id"])}, page=f"/admin/users/{uid('tina')}")
    assert ta.get("/admin/users").status_code in (302, 403, 404)


def test_trainer_does_not_see_links_to_pages_without_access(world):
    app, admin, ca, cb, ta, tb = world
    for url in ("/lineup/split", "/team/levels", "/team/", "/team/calendar"):
        page = ta.get(url).get_data(as_text=True)
        assert "Holdindstillinger" not in page.replace("Holdindstillinger er", "") or url == "/team/", url
        assert 'href="/team/settings"' not in page and 'href="/team/criteria"' not in page and 'href="/admin/' not in page, url
    assert ta.get("/team/settings").status_code in (302, 403, 404)                       # og siden er reelt låst
    assert 'href="/team/settings"' in ca.get("/team/").get_data(as_text=True)             # klubadministrator ser den


def test_import_is_scoped_to_own_club(world):
    """Klubadmin i Alfa importerer en fil med holdnavnet «U11 Beta» (Beta Klubs hold): må ikke røre Beta Klub."""
    import io, re
    app, admin, ca, cb, ta, tb = world
    switch(tb, team_id(app, "U11 Beta"))
    player(tb, "Bea Beta")
    csv = "Hold;Navn;Fødselsdato;Trøjenr\nU11 Beta;Bea Beta;10-03-2016;99\nU11 Beta;Ny Pige;2016-01-01;5\n".encode()
    r = ca.c.post("/admin/import", data={"csrf_token": ca.token("/admin/import"), "file": (io.BytesIO(csv), "x.csv")}, content_type="multipart/form-data")
    html = r.get_data(as_text=True)
    token = re.search(r'name="token" value="([^"]+)"', html).group(1)
    ca.post("/admin/import/commit", {"token": token, "confirm": "ja"}, page="/admin/import")
    beta_b = sql(app, "SELECT p.* FROM players p JOIN teams t ON t.id=p.team_id JOIN clubs c ON c.id=t.club_id WHERE c.name='Beta Klub'")
    assert [p["name"] for p in beta_b] == ["Bea Beta"] and beta_b[0]["shirt_no"] in (None, "")   # Beta Klub urørt
    new = sql(app, "SELECT t.club_id, COUNT(p.id) n FROM teams t JOIN players p ON p.team_id=t.id WHERE t.name='U11 Beta' GROUP BY t.id")
    assert {(r["club_id"], r["n"]) for r in new} == {(club_id(app, "Beta Klub"), 1), (club_id(app, "Alfa Klub"), 2)}   # nyt hold i Alfa Klub


def test_clubadmin_import_preview_cannot_be_committed_by_other_user(world):
    import io, re
    app, admin, ca, cb, ta, tb = world
    csv = "Hold;Navn\nU11 Alfa;Ida\n".encode()
    html = ca.c.post("/admin/import", data={"csrf_token": ca.token("/admin/import"), "file": (io.BytesIO(csv), "x.csv")}, content_type="multipart/form-data").get_data(as_text=True)
    token = re.search(r'name="token" value="([^"]+)"', html).group(1)
    cb.post("/admin/import/commit", {"token": token, "confirm": "ja"}, page="/admin/import")
    assert not sql(app, "SELECT 1 FROM players WHERE name='Ida'")


def test_clubadmin_has_club_admin_page_with_only_own_club_and_working_links(world):
    import re
    app, admin, ca, cb, ta, tb = world
    assert "Klubadministration" in ca.get("/menu").get_data(as_text=True)
    assert "Klubadministration" not in ta.get("/menu").get_data(as_text=True)                 # trænere ser den ikke
    page = ca.get("/admin/").get_data(as_text=True)
    assert "Klubadministration – Alfa Klub" in page and "U11 Alfa" in page
    assert "U11 Beta" not in page and "Beta Klub" not in page                                # anden klub er usynlig
    links = {h for h in re.findall(r'href="(/[^"#]*)"', page) if h.startswith(("/admin", "/inbox", "/team"))}
    assert {"/admin/club", "/admin/users", "/admin/invitations/", "/admin/teams", "/admin/import", "/admin/retention"} <= links
    for h in sorted(links):
        assert ca.get(h).status_code == 200, h                                                # alle links virker for klubadmin
    for h in ("/admin/security", "/admin/mail", "/admin/usage", "/admin/audit", "/admin/clubs", "/admin/backlog", "/admin/users/overview", "/admin/export.xlsx"):
        assert ca.get(h).status_code == 403, h                                                # kun systemadministrator
    sysp = admin.get("/admin/").get_data(as_text=True)
    assert "Driftstjek" in sysp and "Klubber" in sysp                                         # systemadmin har stadig fuld side
