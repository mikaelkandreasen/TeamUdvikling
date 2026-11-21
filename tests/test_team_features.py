"""v0.10.0: holdindstillinger, funktionsvalg, niveau, noter, mascot, holddeling, chef-trænere og invitationer, brugeroversigt."""
import re

import pytest

from app import split, db as appdb
from test_clubs_invites import BASE, code, invite, link, mailapp, sql, world  # noqa: F401  (fixtures)
from conftest import PW, Client
from helpers import add_player, make_team, make_trainer, player_id, switch, team_id


def P(i, level, score=None):
    return dict(id=i, name=f"S{i}", level=level, score=score)


# ----------------------------------------------------------------------------- split (rene funktioner)
def test_split_fills_by_level_and_capacity():
    players = [P(1, "A+", 4), P(2, "A", 3), P(3, "B", 3), P(4, "B", 2), P(5, "C", 3), P(6, "Ny"), P(7, None, 1)]
    teams, left = split.split(players, 2, 0, 1)
    byname = {t["name"]: [p["id"] for p in t["players"]] for t in teams}
    assert byname["A-hold"] == [1, 2]                       # A+/A først
    assert byname["B-hold"] == [3, 4]
    assert byname["C-hold"] == [5, 7] and [p["id"] for p in left] == [6]       # bedste score først; Ny uden score sidst


def test_split_shortage_fills_a_teams_first_and_warns():
    teams, left = split.split([P(1, "A", 3), P(2, "A", 2), P(3, "B", 1)], 3, 1, 3)
    assert [len(t["players"]) for t in teams[:3]] == [3, 0, 0]       # A1 fyldes først
    assert teams[0]["short"] == 0 and teams[1]["short"] == 3 and left == []


def test_split_overflow_of_a_goes_to_b_tier_and_unrated_is_c():
    ps = [P(i, "A", 10 - i) for i in range(1, 7)] + [P(7, None), P(8, "Ny")]
    teams, left = split.split(ps, 2, 0, 1)          # kapacitet 2 pr. hold
    t = {x["tier"]: [p["id"] for p in x["players"]] for x in teams}
    assert t["A"] == [1, 2] and t["B"] == [3, 4] and sorted(t["C"]) == [5, 6]
    assert sorted(p["id"] for p in left) == [7, 8]


# ----------------------------------------------------------------------------- funktioner, niveau, noter, mascot
def test_feature_toggle_hides_and_blocks(app, admin):
    make_team(admin, "A")
    switch(admin, team_id(app, "A"))
    assert admin.get("/devdata/").status_code in (200, 302, 404)
    s = {"game_type": "5v5", "subs": "2", "slogan": "Sammen", "mascot_name": "Bamse", "feat_lineup": "1", "feat_levels": "1", "feat_notes": "1", "feat_mascot": "1"}
    admin.post("/team/settings", s, page="/team/settings")
    assert admin.get("/motivation/").status_code == 404 and admin.get("/devdata/").status_code == 404
    assert admin.get("/team/mascot").status_code == 200
    assert "Sammen" in admin.get("/").get_data(as_text=True)
    admin.post("/team/settings", {**s, "feat_mascot": "", "feat_motivation": "1"}, page="/team/settings")
    assert admin.get("/team/mascot").status_code == 404 and admin.get("/motivation/").status_code == 200


def test_levels_notes_mascot_and_report(app, admin):
    make_team(admin, "A")
    switch(admin, team_id(app, "A"))
    add_player(admin, "Anna Alfa"); add_player(admin, "Bella Beta")
    pa, pb = player_id(app, "Anna Alfa"), player_id(app, "Bella Beta")
    admin.post("/team/levels", {f"level_{pa}": "A+", f"level_{pb}": "Ugyldig"}, page="/team/levels")
    assert sql(app, "SELECT level FROM players WHERE id=?", pa)[0]["level"] == "A+" and sql(app, "SELECT level FROM players WHERE id=?", pb)[0]["level"] is None
    admin.post("/team/notes/add", {"body": "Husk bolde"}, page="/team/notes")
    assert "Husk bolde" in admin.get("/team/notes").get_data(as_text=True)
    admin.post("/team/settings", {"game_type": "5v5", "subs": "1", "feat_mascot": "1", "feat_notes": "1", "feat_levels": "1"}, page="/team/settings")
    for pid, why in ((pa, "indsats"), (pa, "fremgang"), (pb, "indsats")):
        admin.post("/team/mascot", {"player": str(pid), "reason": why, "taken_on": "2026-10-01"}, page="/team/mascot")
    admin.post("/team/mascot", {"player": str(pa), "reason": "ugyldig"}, page="/team/mascot")
    assert sql(app, "SELECT COUNT(*) c FROM mascot_log")[0]["c"] == 3
    rep = admin.get("/team/mascot/report").get_data(as_text=True)
    assert "Anna Alfa" in rep and "Flot indsats (1)" in rep and "3 gange" in rep


def test_split_page_and_save(app, admin):
    make_team(admin, "A")
    switch(admin, team_id(app, "A"))
    for n in "ABCDEFGH":
        add_player(admin, f"Spiller {n}")
    admin.post("/team/settings", {"game_type": "3v3", "subs": "0", "feat_lineup": "1", "feat_levels": "1"}, page="/team/settings")
    ids = [player_id(app, f"Spiller {n}") for n in "ABCDEFGH"]
    admin.post("/team/levels", {f"level_{i}": lv for i, lv in zip(ids, ["A+", "A", "A", "B", "B", "C", "Ny", ""])}, page="/team/levels")
    r = admin.get("/lineup/split?per_tier=1")
    assert r.status_code == 200 and "A-hold" in r.get_data(as_text=True)
    admin.post("/lineup/split", {"action": "save", "per_tier": "1"}, page="/lineup/split?per_tier=1")
    assert {r["name"] for r in sql(app, "SELECT name FROM lineups")} >= {"A-hold", "B-hold", "C-hold"}


def test_team_isolation_for_team_pages(app, admin):
    make_team(admin, "A"); make_team(admin, "B")
    switch(admin, team_id(app, "A")); add_player(admin, "Anna Alfa")
    pa = player_id(app, "Anna Alfa")
    admin.post("/team/settings", {"game_type": "5v5", "subs": "1", "feat_mascot": "1"}, page="/team/settings")
    admin.post("/team/mascot", {"player": str(pa), "reason": "indsats"}, page="/team/mascot")
    admin.post("/team/notes/add", {"body": "kun A"}, page="/team/notes")
    switch(admin, team_id(app, "B"))
    admin.post("/team/settings", {"game_type": "5v5", "subs": "1", "feat_mascot": "1"}, page="/team/settings")
    assert "Anna" not in admin.get("/team/mascot/report").get_data(as_text=True) and "kun A" not in admin.get("/team/notes").get_data(as_text=True)
    mid = sql(app, "SELECT id FROM mascot_log")[0]["id"]
    assert admin.post(f"/team/mascot/{mid}/delete", {}, page="/team/mascot").status_code == 404
    admin.post("/team/mascot", {"player": str(pa), "reason": "indsats"}, page="/team/mascot")      # spiller fra hold A afvises
    assert sql(app, "SELECT COUNT(*) c FROM mascot_log")[0]["c"] == 1


# ----------------------------------------------------------------------------- chef-træner og invitationer
def test_head_coach_permissions_and_invites(world):
    app, admin, ca, cb, ta, tb = world
    tid = team_id(app, "U11 Alfa")
    assert ta.get("/team/settings").status_code == 403 and ta.get("/admin/evaluations").status_code == 403
    assert ta.get("/admin/invitations/").status_code == 403
    ca.post(f"/admin/teams/{tid}/head", {"head_user": [str(sql(app, "SELECT id FROM users WHERE username='tina'")[0]["id"])]}, page="/admin/teams")
    assert ta.get("/team/settings").status_code == 200 and ta.get("/admin/evaluations").status_code == 200
    assert ta.get("/admin/clubs").status_code == 403 and ta.get("/admin/users").status_code == 403
    # chef-træner inviterer en ny chef-træner til eget hold
    data = {"email": "chef@example.dk", "role": "trainer", "as_head": "1", "teams": [str(tid), str(team_id(app, "U11 Beta"))], "code": code(app, ta, "tina")}
    ta.post("/admin/invitations/", data, page="/admin/invitations/", follow_redirects=True)
    row = sql(app, "SELECT * FROM invitations WHERE email='chef@example.dk'")[0]
    assert row["team_ids"] == str(tid) and row["as_head"] == 1          # kun eget hold
    n = Client(app)
    n.c.post(link(app), data={"csrf_token": n.token(link(app)), "username": "chefny", "display_name": "Chef", "password": PW, "password2": PW})
    uid = sql(app, "SELECT id FROM users WHERE username='chefny'")[0]["id"]
    assert sql(app, "SELECT 1 FROM team_heads WHERE team_id=? AND user_id=?", tid, uid)
    # chef-træner kan ikke invitere klubadministrator eller se andres invitationer
    ta.post("/admin/invitations/", {"email": "x@example.dk", "role": "clubadmin", "code": code(app, ta, "tina")}, page="/admin/invitations/")
    assert not sql(app, "SELECT 1 FROM invitations WHERE email='x@example.dk'")
    ta.post("/admin/invitations/", {"email": "y@example.dk", "role": "trainer", "code": code(app, ta, "tina")}, page="/admin/invitations/")
    assert not sql(app, "SELECT 1 FROM invitations WHERE email='y@example.dk'")         # intet hold valgt


def test_clubadmin_can_invite_head_coach(world):
    app, admin, ca, cb, ta, tb = world
    tid = team_id(app, "U11 Alfa")
    ca.post("/admin/invitations/", {"email": "h@example.dk", "role": "trainer", "as_head": "1", "teams": [str(tid)], "code": code(app, ca, "kaja")}, page="/admin/invitations/")
    assert "chef-træner" in app.extensions["outbox"][-1]["body"]


# ----------------------------------------------------------------------------- brugernavn-tjek og brugeroversigt
def test_username_check_and_overview(world):
    app, admin, ca, cb, ta, tb = world
    invite(app, admin, "ny@example.dk", club=1)
    path = link(app)
    n = Client(app)
    assert n.get(path + "/brugernavn?u=tina").get_json()["ok"] is False
    assert n.get(path + "/brugernavn?u=helt-nyt").get_json()["ok"] is True
    assert n.get("/invitation/forkert/brugernavn?u=tina").status_code == 400          # intet åbent opslag
    page = admin.get("/admin/users/overview").get_data(as_text=True)
    assert "tina" in page and "Alfa Klub" in page and "U11 Alfa" in page and "Senest logget ind" in page
    assert sql(app, "SELECT last_login FROM users WHERE username='tina'")[0]["last_login"]
    assert ca.get("/admin/users/overview").status_code == 403


def test_login_branding_only_from_remembered_last_login(world):
    from test_remember import login, tok
    app, admin, ca, cb, ta, tb = world
    sql(app, "UPDATE clubs SET color='#1f3a5f' WHERE id=1")
    c, _ = login(app, "tina", ta.secret, remember=True)
    assert tok(c, "u11_lc") == "1"                                  # husket enhed → klub-cookie
    c2, _ = login(app, "tina", ta.secret, remember=False)
    assert tok(c2, "u11_lc") is None                                # ingen husk → ingen klub-cookie
    anon = Client(app)
    page = anon.get("/login").get_data(as_text=True)
    assert "Alfa Klub" not in page and "--navy2" not in page
    known = app.test_client()
    known.set_cookie("u11_lc", "1")
    assert "--navy2" in known.get("/login").get_data(as_text=True)
