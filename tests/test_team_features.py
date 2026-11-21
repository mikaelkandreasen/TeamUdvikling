"""v0.10.0: holdindstillinger, funktionsvalg, niveau, noter, mascot, holddeling, chef-trænere og invitationer, brugeroversigt."""
import re

import pytest

from app import split, db as appdb
from test_clubs_invites import BASE, code, invite, link, mailapp, player, sql, world  # noqa: F401  (fixtures)
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


# ----------------------------------------------------------------------------- sæsonskifte
def test_season_rollover_copies_players_not_scores_and_archives(app, admin):
    from helpers import score_all
    make_team(admin, "U11")
    switch(admin, team_id(app, "U11"))
    add_player(admin, "Anna Alfa"); add_player(admin, "Bella Beta", active=False)
    pa = player_id(app, "Anna Alfa")
    score_all(admin, 1, pa, 4)
    admin.post("/team/settings", {"game_type": "8v8", "subs": "3", "slogan": "Hurra", "feat_levels": "1"}, page="/team/settings")
    admin.post("/team/levels", {f"level_{pa}": "A"}, page="/team/levels")
    admin.post("/team/season", {"name": "U12", "season": "2027", "players": "1", "trainers": "1", "archive": "1"}, page="/team/season")
    new = team_id(app, "U12")
    rows = sql(app, "SELECT name, level FROM players WHERE team_id=?", new)
    assert [(r["name"], r["level"]) for r in rows] == [("Anna Alfa", "A")]                  # kun aktive, niveau med
    assert sql(app, "SELECT COUNT(*) c FROM evaluations e JOIN players p ON p.id=e.player_id WHERE p.team_id=?", new)[0]["c"] == 0
    assert sql(app, "SELECT COUNT(*) c FROM evaluations")[0]["c"] > 0                       # gammelt hold urørt
    assert sql(app, "SELECT archived FROM teams WHERE id=?", team_id(app, "U11"))[0]["archived"] == 1
    assert sql(app, "SELECT slogan FROM teams WHERE id=?", new)[0]["slogan"] == "Hurra"
    r = admin.get("/team/")
    assert "8v8" in r.get_data(as_text=True)
    # arkiveret hold er skrivebeskyttet
    switch(admin, team_id(app, "U11"))
    assert admin.post("/players/new", {"name": "Ny", "birth_date": "2016-01-01", "position": "Angreb"}, page="/players/new").status_code == 403
    assert admin.get("/players/").status_code == 200
    # genåbn
    admin.post(f"/admin/teams/{team_id(app, 'U11')}/unarchive", {}, page="/admin/teams")
    assert admin.post("/players/new", {"name": "Ny", "birth_date": "2016-01-01", "position": "Angreb", "active": "1"}, page="/players/new").status_code in (200, 302)


def test_season_name_must_be_free_and_needs_permission(world):
    app, admin, ca, cb, ta, tb = world
    ca.post(f"/admin/teams/{team_id(app, 'U11 Alfa')}/archive", {}, page="/admin/teams")
    switch(ca, team_id(app, "U11 Alfa"))
    assert ta.post("/team/season", {"name": "X"}, page="/team/").status_code == 403
    ca.post("/team/season", {"name": "U11 Alfa"}, page="/team/season")                       # navn findes
    assert len(sql(app, "SELECT 1 FROM teams WHERE name='U11 Alfa'")) == 1


# ----------------------------------------------------------------------------- fremmøde pr. træning/kamp
def test_attendance_events_drive_devdata_and_are_team_scoped(app, admin):
    make_team(admin, "A"); make_team(admin, "B")
    switch(admin, team_id(app, "A"))
    add_player(admin, "Anna Alfa"); add_player(admin, "Bella Beta")
    pa, pb = player_id(app, "Anna Alfa"), player_id(app, "Bella Beta")
    for day in ("2026-10-01", "2026-10-08"):
        admin.post("/devdata/fremmoede", {"kind": "training", "day": day}, page="/devdata/fremmoede")
    admin.post("/devdata/fremmoede", {"kind": "match", "day": "2026-10-10"}, page="/devdata/fremmoede")
    e2 = sql(app, "SELECT id FROM att_events WHERE day='2026-10-08'")[0]["id"]
    admin.post(f"/devdata/fremmoede/{e2}", {"present": [str(pa)]}, page=f"/devdata/fremmoede/{e2}")      # Bella var ikke til stede
    page = admin.get("/devdata/").get_data(as_text=True)
    assert "2</b> træninger og <b>1</b> kampe" in page
    assert "100%" in page and "50%" in page                          # Anna 2/2, Bella 1/2
    assert admin.post("/devdata/", {f"trainings_{pa}": "99"}, page="/devdata/").status_code in (200, 302)
    assert sql(app, "SELECT COUNT(*) c FROM att_marks m JOIN att_events e ON e.id=m.event_id WHERE e.kind='training' AND m.player_id=?", pb)[0]["c"] == 1
    switch(admin, team_id(app, "B"))
    assert admin.get(f"/devdata/fremmoede/{e2}").status_code == 404                                       # andet holds registrering
    assert admin.post(f"/devdata/fremmoede/{e2}/delete", {}, page="/devdata/fremmoede").status_code == 404
    assert "Ingen registreringer endnu" in admin.get("/devdata/fremmoede").get_data(as_text=True)


# ----------------------------------------------------------------------------- trivsel over tid
def test_wellbeing_over_time_latest_used_and_chart(app, admin):
    make_team(admin, "A"); make_team(admin, "B")
    switch(admin, team_id(app, "A"))
    add_player(admin, "Anna Alfa")
    pa = player_id(app, "Anna Alfa")
    admin.post("/devdata/trivsel", {"day": "2026-09-01", f"t1_{pa}": "2", f"t2_{pa}": "2", f"t3_{pa}": "2"}, page="/devdata/trivsel")
    assert "Trivsel over tid" not in admin.get(f"/report/{pa}").get_data(as_text=True)        # kun én måling
    admin.post("/devdata/trivsel", {"day": "2026-10-15", f"t1_{pa}": "4", f"t2_{pa}": "5", f"t3_{pa}": "", "x": "1"}, page="/devdata/trivsel")
    assert sql(app, "SELECT COUNT(*) c FROM wellbeing")[0]["c"] == 2
    page = admin.get("/devdata/").get_data(as_text=True)
    assert 'value="4"' in page and 'value="5"' in page                         # seneste måling vises
    assert "Trivsel over tid" in admin.get(f"/report/{pa}").get_data(as_text=True)
    admin.post("/devdata/trivsel", {"day": "2026-10-15", f"t1_{pa}": "", f"t2_{pa}": "", f"t3_{pa}": ""}, page="/devdata/trivsel")
    assert sql(app, "SELECT COUNT(*) c FROM wellbeing")[0]["c"] == 1             # tomme felter fjerner målingen
    switch(admin, team_id(app, "B"))
    assert "Tidligere målinger" not in admin.get("/devdata/trivsel").get_data(as_text=True)    # hold B ser ikke hold A's målinger


# ----------------------------------------------------------------------------- assistent (læseadgang)
def test_readonly_assistant_can_read_but_not_write(world):
    app, admin, ca, cb, ta, tb = world
    uid = sql(app, "SELECT id FROM users WHERE username='tina'")[0]["id"]
    switch(ca, team_id(app, "U11 Alfa"))
    player(ca, "Anna Alfa")
    ca.post(f"/admin/users/{uid}/readonly", {"readonly": "1"}, page="/admin/users")
    assert sql(app, "SELECT readonly FROM users WHERE id=?", uid)[0]["readonly"] == 1
    assert ta.get("/players/").status_code == 200 and "Anna Alfa" in ta.get("/players/").get_data(as_text=True)
    assert ta.post("/players/new", {"name": "X", "birth_date": "2016-01-01", "position": "Angreb"}, page="/players/new").status_code == 403
    assert ta.post("/team/notes/add", {"body": "x"}, page="/team/notes").status_code == 403
    assert ta.get("/account").status_code == 200                                  # egen konto (adgangskode/2FA) må stadig tilgås
    assert not sql(app, "SELECT 1 FROM players WHERE name='X'")
    ca.post(f"/admin/users/{uid}/readonly", {}, page="/admin/users")
    assert sql(app, "SELECT readonly FROM users WHERE id=?", uid)[0]["readonly"] == 0


def test_invite_as_readonly_assistant(world):
    app, admin, ca, cb, ta, tb = world
    tid = team_id(app, "U11 Alfa")
    ca.post("/admin/invitations/", {"email": "ass@example.dk", "role": "trainer", "as_readonly": "1", "as_head": "1", "teams": [str(tid)], "code": code(app, ca, "kaja")}, page="/admin/invitations/")
    row = sql(app, "SELECT * FROM invitations WHERE email='ass@example.dk'")[0]
    assert row["as_readonly"] == 1 and row["as_head"] == 0                       # assistent kan ikke samtidig være chef-træner
    assert "assistent" in app.extensions["outbox"][-1]["body"]
    n = Client(app)
    n.c.post(link(app), data={"csrf_token": n.token(link(app)), "username": "assi", "display_name": "A", "password": PW, "password2": PW})
    assert sql(app, "SELECT readonly FROM users WHERE username='assi'")[0]["readonly"] == 1


# ----------------------------------------------------------------------------- spillerlink
def test_player_link_single_use_expiry_and_scope(app, admin):
    make_team(admin, "A"); make_team(admin, "B")
    switch(admin, team_id(app, "A"))
    add_player(admin, "Anna Alfa"); add_player(admin, "Bella Beta")
    pa, pb = player_id(app, "Anna Alfa"), player_id(app, "Bella Beta")
    r = admin.post("/motivation/links", {"player": str(pa)}, page="/motivation/links")
    url = re.search(r'value="https?://[^"/]+(/svar/[\w-]+)"', r.get_data(as_text=True)).group(1)
    assert sql(app, "SELECT COUNT(*) c FROM player_links WHERE token_hash LIKE '%svar%'")[0]["c"] == 0   # token gemmes ikke i klartekst
    anon = Client(app)
    page = anon.get(url).get_data(as_text=True)
    assert "Hej Anna" in page and "Bella" not in page and "Teamoversigt" not in page            # kun dette skema, ingen menu/andre data
    q = sql(app, "SELECT qidx FROM motivation_questions WHERE text<>'' ORDER BY qidx")[0]["qidx"]
    assert anon.get(url).status_code == 200                                                    # GET forbruger ikke linket
    r2 = anon.post(url, {f"q{q}": "4"}, page=url)
    assert r2.status_code == 200 and "Tak for dine svar" in r2.get_data(as_text=True)
    assert sql(app, "SELECT score FROM motivation_answers WHERE player_id=? AND qidx=?", pa, q)[0]["score"] == 4
    assert anon.get(url).status_code == 400 and anon.post(url, {f"q{q}": "1"}, page=url).status_code in (400, 429)   # engangslink
    assert sql(app, "SELECT score FROM motivation_answers WHERE player_id=? AND qidx=?", pa, q)[0]["score"] == 4
    # udløb og tilbagekaldelse
    admin.post("/motivation/links", {"player": str(pb)}, page="/motivation/links")
    sql(app, "UPDATE player_links SET expires_at=1 WHERE player_id=?", pb)
    assert "udløbet" in admin.get("/motivation/links").get_data(as_text=True)
    assert Client(app).get("/svar/forkert-token").status_code == 400
    # hold B kan ikke oprette link til hold A's spiller eller tilbagekalde andres
    switch(admin, team_id(app, "B"))
    assert admin.post("/motivation/links", {"player": str(pa)}, page="/motivation/links").status_code == 404
    lid = sql(app, "SELECT id FROM player_links LIMIT 1")[0]["id"]
    assert admin.post(f"/motivation/links/{lid}/revoke", {}, page="/motivation/links").status_code == 404
    # funktion slået fra → linket virker ikke
    switch(admin, team_id(app, "A"))
    r = admin.post("/motivation/links", {"player": str(pa)}, page="/motivation/links")
    url2 = re.search(r'value="https?://[^"/]+(/svar/[\w-]+)"', r.get_data(as_text=True)).group(1)
    admin.post("/team/settings", {"game_type": "5v5", "subs": "1"}, page="/team/settings")      # alle funktioner fra
    assert Client(app).get(url2).status_code == 400
