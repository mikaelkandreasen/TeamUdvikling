import datetime
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
    players = [P(1, "A", 4), P(2, "A", 3), P(3, "B", 3), P(4, "B", 2), P(5, "C", 3), P(6, "D"), P(7, None, 1)]
    teams, left = split.split(players, 2, 0, 1)
    byname = {t["name"]: [p["id"] for p in t["players"]] for t in teams}
    assert byname["A-hold"] == [1, 2]                       # A først
    assert byname["B-hold"] == [3, 4]
    assert byname["C-hold"] == [5, 7] and [p["id"] for p in left] == [6]       # bedste score først; Ny uden score sidst


def test_split_shortage_fills_a_teams_first_and_warns():
    teams, left = split.split([P(1, "A", 3), P(2, "A", 2), P(3, "B", 1)], 3, 1, 3)
    assert [len(t["players"]) for t in teams[:3]] == [3, 0, 0]       # A1 fyldes først
    assert teams[0]["short"] == 0 and teams[1]["short"] == 3 and left == []


def test_split_overflow_of_a_goes_to_b_tier_and_unrated_is_c():
    ps = [P(i, "A", 10 - i) for i in range(1, 7)] + [P(7, None), P(8, "D")]
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
    assert "Sammen" in admin.get("/?hold=1").get_data(as_text=True)
    admin.post("/team/settings", {**s, "feat_mascot": "", "feat_motivation": "1"}, page="/team/settings")
    assert admin.get("/team/mascot").status_code == 404 and admin.get("/motivation/").status_code == 200


def test_levels_notes_mascot_and_report(app, admin):
    make_team(admin, "A")
    switch(admin, team_id(app, "A"))
    add_player(admin, "Anna Alfa"); add_player(admin, "Bella Beta")
    pa, pb = player_id(app, "Anna Alfa"), player_id(app, "Bella Beta")
    admin.post("/team/levels", {f"level_{pa}": "A", f"level_{pb}": "Ugyldig"}, page="/team/levels")
    assert sql(app, "SELECT level FROM players WHERE id=?", pa)[0]["level"] == "A" and sql(app, "SELECT level FROM players WHERE id=?", pb)[0]["level"] is None
    admin.post("/team/notes/add", {"title": "Bolde", "note_date": "2026-11-20", "body": "Husk bolde"}, page="/team/notes")
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
    admin.post("/team/levels", {f"level_{i}": lv for i, lv in zip(ids, ["A", "A", "A", "B", "B", "C", "D", ""])}, page="/team/levels")
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
    tid = team_id(app, "Hold Alfa")
    assert ta.get("/team/settings").status_code == 403 and ta.get("/admin/evaluations").status_code == 403
    assert ta.get("/admin/invitations/").status_code == 403
    ca.post(f"/admin/teams/{tid}/head", {"head_user": [str(sql(app, "SELECT id FROM users WHERE username='tina'")[0]["id"])]}, page="/admin/teams")
    assert ta.get("/team/settings").status_code == 200 and ta.get("/admin/evaluations").status_code == 200
    assert ta.get("/admin/clubs").status_code == 403 and ta.get("/admin/users").status_code == 403
    # chef-træner kan invitere trænere og assistenter (aldrig chef-trænere) til eget hold
    data = {"email": "chef@example.dk", "role": "trainer", "as_head": "1", "teams": [str(tid), str(team_id(app, "Hold Beta"))], "code": code(app, ta, "tina")}
    ta.post("/admin/invitations/", data, page="/admin/invitations/", follow_redirects=True)
    row = sql(app, "SELECT * FROM invitations WHERE email='chef@example.dk'")[0]
    assert row["team_ids"] == str(tid) and row["as_head"] == 0 and row["as_readonly"] == 0   # kun eget hold, aldrig chef-træner
    n = Client(app)
    n.c.post(link(app), data={"csrf_token": n.token(link(app)), "username": "chefny", "display_name": "Chef", "password": PW, "password2": PW})
    uid = sql(app, "SELECT id FROM users WHERE username='chefny'")[0]["id"]
    assert not sql(app, "SELECT 1 FROM team_heads WHERE team_id=? AND user_id=?", tid, uid)
    assert sql(app, "SELECT readonly FROM users WHERE id=?", uid)[0]["readonly"] == 0
    ta.post("/admin/invitations/", {"email": "ass2@example.dk", "role": "trainer", "as_readonly": "1", "teams": [str(tid)], "code": code(app, ta, "tina")}, page="/admin/invitations/")
    assert sql(app, "SELECT as_readonly FROM invitations WHERE email='ass2@example.dk'")[0]["as_readonly"] == 1
    # chef-træner kan ikke invitere klubadministrator eller se andres invitationer
    ta.post("/admin/invitations/", {"email": "x@example.dk", "role": "clubadmin", "code": code(app, ta, "tina")}, page="/admin/invitations/")
    assert not sql(app, "SELECT 1 FROM invitations WHERE email='x@example.dk'")
    ta.post("/admin/invitations/", {"email": "y@example.dk", "role": "trainer", "as_readonly": "1", "code": code(app, ta, "tina")}, page="/admin/invitations/")
    assert not sql(app, "SELECT 1 FROM invitations WHERE email='y@example.dk'")         # intet hold valgt


def test_clubadmin_can_invite_head_coach(world):
    app, admin, ca, cb, ta, tb = world
    tid = team_id(app, "Hold Alfa")
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
    assert "tina" in page and "Alfa Klub" in page and "Hold Alfa" in page and "Senest logget ind" in page
    assert sql(app, "SELECT last_login FROM users WHERE username='tina'")[0]["last_login"]
    assert ca.get("/admin/users/overview").status_code == 403


def test_login_branding_only_from_remembered_last_login(world):
    from test_remember import login, tok
    app, admin, ca, cb, ta, tb = world
    sql(app, "UPDATE clubs SET color='#1f3a5f' WHERE id=1")
    c, _ = login(app, "tina", ta.secret, remember=True)
    assert tok(c, "teamudvikling_lc") == "1"                                  # husket enhed → klub-cookie
    c2, _ = login(app, "tina", ta.secret, remember=False)
    assert tok(c2, "teamudvikling_lc") is None                                # ingen husk → ingen klub-cookie
    anon = Client(app)
    page = anon.get("/login").get_data(as_text=True)
    assert "Alfa Klub" not in page and "--navy2" not in page
    known = app.test_client()
    known.set_cookie("teamudvikling_lc", "1")
    assert "--navy2" in known.get("/login").get_data(as_text=True)


# ----------------------------------------------------------------------------- sæsonskifte
def test_season_rollover_copies_players_not_scores_and_archives(app, admin):
    from helpers import score_all
    make_team(admin, "Hold U")
    switch(admin, team_id(app, "Hold U"))
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
    assert sql(app, "SELECT archived FROM teams WHERE id=?", team_id(app, "Hold U"))[0]["archived"] == 1
    assert sql(app, "SELECT slogan FROM teams WHERE id=?", new)[0]["slogan"] == "Hurra"
    r = admin.get("/team/")
    assert "8v8" in r.get_data(as_text=True)
    # arkiveret hold er skrivebeskyttet
    switch(admin, team_id(app, "Hold U"))
    assert admin.post("/players/new", {"name": "Ny", "birth_date": "2016-01-01", "position": "Angreb"}, page="/players/new").status_code == 403
    assert admin.get("/players/").status_code == 200
    # genåbn
    admin.post(f"/admin/teams/{team_id(app, 'Hold U')}/unarchive", {}, page="/admin/teams")
    assert admin.post("/players/new", {"name": "Ny", "birth_date": "2016-01-01", "position": "Angreb", "active": "1"}, page="/players/new").status_code in (200, 302)


def test_season_name_must_be_free_and_needs_permission(world):
    app, admin, ca, cb, ta, tb = world
    ca.post(f"/admin/teams/{team_id(app, 'Hold Alfa')}/archive", {}, page="/admin/teams")
    switch(ca, team_id(app, "Hold Alfa"))
    assert ta.post("/team/season", {"name": "X"}, page="/team/").status_code == 403
    ca.post("/team/season", {"name": "Hold Alfa"}, page="/team/season")                       # navn findes
    assert len(sql(app, "SELECT 1 FROM teams WHERE name='Hold Alfa'")) == 1


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
    switch(ca, team_id(app, "Hold Alfa"))
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
    tid = team_id(app, "Hold Alfa")
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


# ----------------------------------------------------------------------------- opbevaringsfrist
def test_retention_is_club_scoped_and_deadline_based(world):
    app, admin, ca, cb, ta, tb = world
    switch(ca, team_id(app, "Hold Alfa")); switch(cb, team_id(app, "Hold Beta"))
    for c, n in ((ca, "Alfa Inaktiv"), (cb, "Beta Inaktiv")):
        c.post("/players/new", {"name": n, "birth_date": "2016-03-10", "position": "Angreb"}, page="/players/new")       # active udeladt = inaktiv
    assert sql(app, "SELECT COUNT(*) c FROM players WHERE active=0 AND deactivated_at IS NOT NULL")[0]["c"] == 2
    admin.post("/admin/retention", {"action": "settings", "months": "6", "auto": "1"}, page="/admin/retention")
    sql(app, "UPDATE players SET deactivated_at='2020-01-01' WHERE name='Alfa Inaktiv'")
    assert "over fristen" in ca.get("/admin/retention").get_data(as_text=True)
    assert ca.post("/admin/retention", {"action": "settings", "months": "0"}, page="/admin/retention").status_code == 403   # kun systemadministrator
    ca.post("/admin/retention", {"action": "delete_all", "confirm": "ja"}, page="/admin/retention")
    names = {r["name"] for r in sql(app, "SELECT name FROM players")}
    assert "Alfa Inaktiv" not in names and "Beta Inaktiv" in names                                # klubadministrator rammer kun egen klub
    sql(app, "UPDATE players SET deactivated_at='2020-01-01' WHERE name='Beta Inaktiv'")
    from app import db as appdb
    con = appdb.connect(app.config["DATABASE"]); appdb.purge_old(con); con.close()                 # automatisk sletning ved fristens udløb
    assert "Beta Inaktiv" not in {r["name"] for r in sql(app, "SELECT name FROM players")}


# ----------------------------------------------------------------------------- sikkerhedslog
def test_security_log_records_failures_and_ip_blocks(app, admin):
    from app import auth
    make_team(admin, "A")
    make_trainer(app, admin, "tr", ["A"])
    c = Client(app)
    for _ in range(3):
        c.login("tr", "forkert-adgangskode-123")
    page = admin.get("/admin/security").get_data(as_text=True)
    assert "login_fejl" in page or "konto_låst" in page or "Ingen hændelser" not in page
    for _ in range(30):                                                  # IP-begrænsning slår til
        c.c.post("/login", data={"username": "tr", "password": "x", "csrf_token": c.token()})
    assert "ip_blokeret" in admin.get("/admin/security").get_data(as_text=True)
    assert Client(app).get("/admin/security").status_code in (302, 403)


# ----------------------------------------------------------------------------- egne kriterietekster
def test_team_criteria_override_and_isolation(app, admin):
    from app import model
    make_team(admin, "A"); make_team(admin, "B")
    switch(admin, team_id(app, "A"))
    add_player(admin, "Anna Alfa")
    pa = player_id(app, "Anna Alfa")
    data = {f"desc_{c['idx']}": c["desc"] for c in model.CRITERIA}
    data["desc_0"] = "Vores egen tekst om teknik"
    admin.post("/team/criteria", data, page="/team/criteria")
    assert "Vores egen tekst om teknik" in admin.get("/criteria").get_data(as_text=True)
    assert "Vores egen tekst om teknik" in admin.get(f"/eval/1/{pa}").get_data(as_text=True)
    assert sql(app, "SELECT COUNT(*) c FROM team_criteria")[0]["c"] == 1          # kun ændrede tekster gemmes
    switch(admin, team_id(app, "B"))
    assert "Vores egen tekst om teknik" not in admin.get("/criteria").get_data(as_text=True)                                # andet hold urørt
    switch(admin, team_id(app, "A"))
    data["desc_0"] = ""
    admin.post("/team/criteria", data, page="/team/criteria")
    assert "Vores egen tekst om teknik" not in admin.get("/criteria").get_data(as_text=True)                                # tom = standard


# ----------------------------------------------------------------------------- iCal
ICS = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:a1
DTSTART:{past}T170000
SUMMARY:Træning på banen
END:VEVENT
BEGIN:VEVENT
UID:a2
DTSTART;VALUE=DATE:{past2}
SUMMARY:Kamp mod Alfa IF\\, hjemme
LOCATION:Virring
 Stadion
END:VEVENT
BEGIN:VEVENT
UID:a3
DTSTART:{future}T100000Z
SUMMARY:Stævne
STATUS:CANCELLED
END:VEVENT
BEGIN:VEVENT
UID:a4
DTSTART:{future}T100000Z
SUMMARY:Kamp mod Beta
END:VEVENT
END:VCALENDAR
"""


def test_ical_parse_folding_cancelled_and_kind():
    from app import ical
    ev = ical.parse(ICS.format(past="20260101", past2="20260102", future="20990101"))
    assert [e["summary"] for e in ev] == ["Træning på banen", "Kamp mod Alfa IF, hjemme", "Kamp mod Beta"]          # aflyst fjernet
    assert ev[0]["time"] == "17:00" and ev[1]["location"] == "VirringStadion" and ev[1]["time"] == ""
    assert [ical.kind_of(e["summary"]) for e in ev] == ["training", "match", "match"]


def test_ical_url_must_be_public_https(monkeypatch):
    from app import ical
    for bad in ("http://example.com/x.ics", "https://user:pw@example.com/x.ics", "https://example.com:8443/x.ics", "ftp://x", ""):
        with pytest.raises(ical.FeedError):
            ical.check_url(bad)
    monkeypatch.setattr(ical.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(ical.FeedError):
        ical.check_url("https://intern.example.com/x.ics")
    monkeypatch.setattr(ical.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("169.254.169.254", 443))])
    with pytest.raises(ical.FeedError):
        ical.check_url("https://metadata.example.com/x.ics")
    monkeypatch.setattr(ical.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    assert ical.check_url("https://example.com/x.ics")


def test_calendar_refresh_and_import_past_as_attendance(app, admin, monkeypatch):
    import datetime
    from app import ical
    make_team(admin, "A")
    switch(admin, team_id(app, "A"))
    add_player(admin, "Anna Alfa")
    monkeypatch.setattr(ical.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    admin.post("/team/settings", {"game_type": "5v5", "subs": "1", "ical_url": "http://intern/x.ics", "feat_devdata": "1"}, page="/team/settings")
    assert not sql(app, "SELECT 1 FROM settings WHERE key LIKE '%ical_url' AND value<>''")                        # http afvist
    admin.post("/team/settings", {"game_type": "5v5", "subs": "1", "ical_url": "https://example.com/k.ics", "feat_devdata": "1"}, page="/team/settings")
    today = datetime.date.today()
    text = ICS.format(past=(today - datetime.timedelta(days=3)).strftime("%Y%m%d"), past2=(today - datetime.timedelta(days=5)).strftime("%Y%m%d"), future=(today + datetime.timedelta(days=30)).strftime("%Y%m%d"))
    monkeypatch.setattr(ical, "fetch", lambda url: text)
    admin.post("/team/calendar", {"action": "refresh"}, page="/team/calendar")
    page = admin.get("/team/calendar").get_data(as_text=True)
    assert "Kamp mod Beta" in page and "Stævne" not in page
    assert "Afholdte uden fremmøde" in page
    admin.post("/team/calendar", {"action": "import", "ev": ["0", "1", "99", "x"]}, page="/team/calendar")
    kinds = {r["kind"] for r in sql(app, "SELECT kind FROM att_events")}
    assert kinds == {"training", "match"} and sql(app, "SELECT COUNT(*) c FROM att_marks")[0]["c"] == 2
    admin.post("/team/calendar", {"action": "import", "ev": ["0", "1"]}, page="/team/calendar")                    # ingen dubletter
    assert sql(app, "SELECT COUNT(*) c FROM att_events")[0]["c"] == 2


def test_user_resets_require_fresh_admin_code(app, admin):
    from app import db as appdb, totp
    make_team(admin, "A")
    make_trainer(app, admin, "tr", ["A"])
    uid = sql(app, "SELECT id FROM users WHERE username='tr'")[0]["id"]
    hash0 = sql(app, "SELECT pw_hash FROM users WHERE id=?", uid)[0]["pw_hash"]
    admin.post(f"/admin/users/{uid}/reset-password", {}, page="/admin/users")                       # uden kode
    admin.post(f"/admin/users/{uid}/reset-2fa", {"code": "000000"}, page="/admin/users")           # forkert kode
    assert sql(app, "SELECT pw_hash FROM users WHERE id=?", uid)[0]["pw_hash"] == hash0
    assert sql(app, "SELECT totp_enabled FROM users WHERE id=?", uid)[0]["totp_enabled"] == 1
    admin.post(f"/admin/users/{uid}/reset-password", {"code": code(app, admin)}, page="/admin/users")
    assert sql(app, "SELECT pw_hash FROM users WHERE id=?", uid)[0]["pw_hash"] != hash0


def test_focus_page_changes_text_and_manifest(app, admin):
    """Træningsfokus, 'siden sidste runde' og neutral PWA-manifest (ingen klubdata, ingen service worker)."""
    import os
    from helpers import score_all
    make_team(admin, "A")
    switch(admin, team_id(app, "A"))
    assert "Der er ikke evalueringer endnu" in admin.get("/team/focus").get_data(as_text=True)
    add_player(admin, "Anna Alfa")
    pid = player_id(app, "Anna Alfa")
    score_all(admin, 1, pid, 2)
    score_all(admin, 2, pid, 4)
    page = admin.get("/team/focus").get_data(as_text=True)
    assert "Holdets laveste områder" in page and "1 spillere" in page
    prof = admin.get(f"/profile/{pid}?runde=2").get_data(as_text=True)
    assert "Siden" in prof and "Samlet op med 2,0" in prof and "▲" in prof
    assert "Udskriv opstilling" not in prof
    m = admin.get("/static/manifest.webmanifest")
    assert m.status_code == 200 and b"Team Udvikling" in m.data and b"club" not in m.data.lower()
    assert admin.get("/static/icon-192.png").status_code == 200
    assert b"manifest.webmanifest" in admin.get("/team/").data
    assert not [f for f in os.listdir(os.path.join(app.root_path, "static")) if f.endswith(".js") and "sw" in f.lower()]


def test_testmail_and_pwned_check(app, admin, monkeypatch):
    from app import auth
    app.config.update(MAIL_BACKEND="memory", PUBLIC_URL="https://t.example", SMTP_FROM="noreply@t.example")
    sql(app, "UPDATE users SET email=NULL WHERE username='admin'")
    assert "ingen e-mailadresse" in admin.post("/admin/testmail", {}, page="/admin/", follow_redirects=True).get_data(as_text=True)
    sql(app, "UPDATE users SET email='admin@example.dk' WHERE username='admin'")
    assert "Prøvemail sendt" in admin.post("/admin/testmail", {}, page="/admin/", follow_redirects=True).get_data(as_text=True)
    assert app.extensions["outbox"][-1]["to"] == "admin@example.dk"
    with app.app_context():
        assert auth.pwned_count("password") == 0                      # slået fra som standard
        app.config["PWNED_CHECK"] = True
        import hashlib, io
        h = hashlib.sha1(b"hemmelig-test").hexdigest().upper()

        class R(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: R(f"{h[5:]}:42\r\n0000000000000000000000000000000000A:0".encode()))
        assert auth.pwned_count("hemmelig-test") == 42
        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("net")))
        assert auth.pwned_count("hemmelig-test") == 0                 # fail-open


def test_distribute_levels_25_50_25():
    from app import model
    d = model.distribute_levels({i: float(i) for i in range(1, 9)})
    assert sorted(d.values()) == ["A", "A", "B", "B", "B", "B", "C", "C"] and d[8] == "A" and d[1] == "C"
    assert set(model.distribute_levels({1: 3, 2: 3, 3: 3}).values()) == {"B"}          # alle ens
    assert model.distribute_levels({1: 4}) == {1: "B"} and model.distribute_levels({}) == {}
    assert model.distribute_levels({1: 5, 2: 1, 3: None}) == {1: "A", 2: "C"}


def test_trainer_level_rating_is_dropdown_and_calculated_automatically(app, admin):
    make_team(admin, "A")
    switch(admin, team_id(app, "A"))
    names = [f"Spiller {c}" for c in "ABCDEFGH"]
    for n in names:
        add_player(admin, n)
    given = ["Nystartet", "D", "C", "B", "B", "A", "A+", "A+"]
    for n, lv in zip(names, given):
        pid = player_id(app, n)
        admin.post(f"/eval/1/{pid}", {"level": lv}, page=f"/eval/1/{pid}")
    admin.post(f"/eval/1/{player_id(app, 'Spiller A')}", {"level": "Ugyldig"}, page="/eval/1/1")                # ugyldigt niveau gemmes ikke
    assert sql(app, "SELECT COUNT(*) c FROM level_ratings WHERE level='Ugyldig'")[0]["c"] == 0
    admin.post(f"/eval/1/{player_id(app, 'Spiller A')}", {"level": "Nystartet"}, page="/eval/1/1")
    form = admin.get(f"/eval/1/{player_id(app, 'Spiller A')}").get_data(as_text=True)
    assert '<select id="lvl" name="level">' in form and "D (nybegynder)" in form and "Nystartet" in form and "A+" in form
    page = admin.get("/team/levels").get_data(as_text=True)
    assert "A: <b>2</b> · B: <b>4</b> · C: <b>2</b>" in page and "Brug beregnet" not in page            # automatisk – ingen knap
    # andelen kan justeres under holdindstillinger (her 12 % A og 40 % C; to A+ har samme score og følger hinanden)
    base = {"game_type": "5v5", "subs": "1", "feat_levels": "1", "level_share_a": "12", "level_share_c": "40"}
    admin.post("/team/settings", base, page="/team/settings")
    page = admin.get("/team/levels").get_data(as_text=True)
    assert "A: <b>2</b> · B: <b>3</b> · C: <b>3</b>" in page and "12 %" in page
    admin.post("/team/settings", dict(base, level_share_a="99"), page="/team/settings")                          # uden for 0-45 afvises
    assert "A: <b>2</b> · B: <b>3</b>" in admin.get("/team/levels").get_data(as_text=True)
    # en træner kan rydde sin vurdering igen
    pid = player_id(app, "Spiller A")
    admin.post(f"/eval/1/{pid}", {"level": ""}, page=f"/eval/1/{pid}")
    assert sql(app, "SELECT COUNT(*) c FROM level_ratings WHERE player_id=?", pid)[0]["c"] == 0


def test_calculated_level_is_used_by_split_when_no_manual_level(app, admin):
    make_team(admin, "A")
    switch(admin, team_id(app, "A"))
    for k, n in enumerate("ABCDEFGH"):
        add_player(admin, f"Spiller {n}")
        pid = player_id(app, f"Spiller {n}")
        admin.post(f"/eval/1/{pid}", {"level": ("Nystartet", "D", "C", "C", "B", "B", "A", "A+")[k]}, page=f"/eval/1/{pid}")
    assert "har ikke noget niveau" not in admin.get("/lineup/split").get_data(as_text=True)               # beregnet niveau er reserve
    admin.post("/players/new", {"name": "Ny Uden", "birth_date": "2016-01-01", "active": "1"}, page="/players/new")
    assert "har ikke noget niveau" in admin.get("/lineup/split").get_data(as_text=True)


def test_levels_a_plus_to_nystartet_help_box_and_migration(app, admin):
    from app import model
    assert model.LEVELS == ("A+", "A", "B", "C", "D", "Nystartet") and [x[0] for x in model.LEVEL_INFO] == list(model.LEVELS)
    assert "dbufyn.dk" in model.LEVEL_SOURCE
    make_team(admin, "A")
    switch(admin, team_id(app, "A"))
    add_player(admin, "Anna Alfa"); add_player(admin, "Bella Beta")
    sql(app, "UPDATE players SET level='Ny' WHERE name='Bella Beta'")
    sql(app, "UPDATE players SET level='A+' WHERE name='Anna Alfa'")
    # gammel tabelform (tal 1-5) omsættes til niveauer, og migrationen kan køres igen
    con = appdb.connect(app.config["DATABASE"])
    con.execute("DROP TABLE level_ratings")
    con.execute("CREATE TABLE level_ratings(round INTEGER NOT NULL, player_id INTEGER NOT NULL, trainer_id INTEGER NOT NULL, score INTEGER NOT NULL, PRIMARY KEY(round, player_id, trainer_id))")
    con.execute("INSERT INTO level_ratings VALUES(1, ?, 1, 5)", (player_id(app, "Anna Alfa"),))
    appdb._migrate_dbu_levels(con); appdb._migrate_dbu_levels(con); con.commit(); con.close()
    assert {r["name"]: r["level"] for r in sql(app, "SELECT name, level FROM players")} == {"Anna Alfa": "A+", "Bella Beta": "Nystartet"}
    assert sql(app, "SELECT level FROM level_ratings")[0]["level"] == "A"
    page = admin.get("/team/levels").get_data(as_text=True)
    assert 'class="helpbox"' in page and "Nystartet" in page and "dbufyn.dk" in page
    assert 'class="helpbox"' in admin.get(f"/eval/1/{player_id(app, 'Anna Alfa')}").get_data(as_text=True)


def test_dbu_rule_all_a_is_a_plus_otherwise_predominant():
    from app import model
    assert model.dbu_result(set()) is None and model.dbu_result({"findes.ikke"}) is None
    assert len(model.DBU_ITEMS) == 10 and len(model.DBU_KEYS) == 40
    assert model.dbu_result({f"{k}.A" for k, _, _ in model.DBU_ITEMS})["level"] == "A+"                  # alle ti scoret A
    nine = {f"{k}.A" for k, _, _ in model.DBU_ITEMS[:9]}
    assert model.dbu_result(nine)["level"] == "A"                                                       # kun ni vurderet → ikke A+
    assert model.dbu_result(nine | {"fysik.B"})["level"] == "A"                                         # overvejende A
    mix = {"engagement.B", "interesse.B", "viden.B", "teknik.A", "spark.C", "motorik.D"}
    assert model.dbu_result(mix)["level"] == "B"
    assert model.dbu_result({"engagement.B", "interesse.C"})["level"] == "B"                           # lighed → det højeste
    assert model.dbu_result({"spark.D", "teknik.D", "fysik.C"})["level"] == "D"


def test_dbu_choices_are_saved_per_trainer_and_drive_calculated_level(app, admin):
    from app import model
    make_team(admin, "A")
    switch(admin, team_id(app, "A"))
    names = [f"Spiller {c}" for c in "ABCDEFGH"]
    for n in names:
        add_player(admin, n)
    keys = [k for k, _, _ in model.DBU_ITEMS]

    def post(n, choice_by_key):
        pid = player_id(app, n)
        data = {"dbu_present": "1"}
        data.update({f"dbu_{k}": v for k, v in choice_by_key.items()})
        return admin.post(f"/eval/1/{pid}", data, page=f"/eval/1/{pid}")

    allx = lambda x: {k: x for k in keys}
    plan = [allx("D"), allx("D"), allx("C"), allx("C"), allx("B"), allx("B"), dict(allx("A"), fysik="B"), allx("A")]
    for n, c in zip(names, plan):
        post(n, c)
    post("Spiller A", {"engagement": "Ugyldig", "interesse": "D"})                                       # ugyldigt valg gemmes ikke
    assert sql(app, "SELECT COUNT(*) c FROM dbu_checks WHERE item LIKE '%Ugyldig%'")[0]["c"] == 0
    post("Spiller A", allx("D"))
    assert sql(app, "SELECT COUNT(*) c FROM dbu_checks WHERE player_id=?", player_id(app, "Spiller H"))[0]["c"] == 10
    form = admin.get(f"/eval/1/{player_id(app, 'Spiller H')}").get_data(as_text=True)
    assert "Dine valg giver: A+-spiller" in form and 'type="radio" name="dbu_engagement" value="A" checked' in form
    page = admin.get("/team/levels").get_data(as_text=True)
    assert "A: <b>2</b> · B: <b>4</b> · C: <b>2</b>" in page                                           # uden dropdown bruges DBU-valgene
    # dropdown vejer tungere; at vælge «ikke vurderet» overalt rydder valgene igen
    pid = player_id(app, "Spiller A")
    post("Spiller A", {})
    assert sql(app, "SELECT COUNT(*) c FROM dbu_checks WHERE player_id=?", pid)[0]["c"] == 0
    assert "Holdsammensætning" in admin.get("/team/levels").get_data(as_text=True)


def test_wiki_notes_dated_shared_editable_searchable_and_team_scoped(app, admin):
    make_team(admin, "A"); make_team(admin, "B")
    switch(admin, team_id(app, "A"))
    admin.post("/team/notes/add", {"title": "Træning 12. nov", "note_date": "2026-11-12", "body": "Presspil og afleveringer"}, page="/team/notes/new")
    admin.post("/team/notes/add", {"body": "Kun en tekst uden titel", "note_date": "ugyldig"}, page="/team/notes/new")          # titel udledes, dato falder tilbage til i dag
    rows = sql(app, "SELECT * FROM team_notes ORDER BY id")
    assert rows[0]["note_date"] == "2026-11-12" and rows[1]["title"] == "Kun en tekst uden titel" and rows[1]["note_date"] == datetime.date.today().isoformat()
    nid = rows[0]["id"]
    page = admin.get("/team/notes").get_data(as_text=True)
    assert "Træning 12. nov" in page and "2026-11-12" in page and "Ny note" in page
    assert "Træning 12. nov" in admin.get("/team/notes?q=presspil").get_data(as_text=True) and "Kun en tekst" not in admin.get("/team/notes?q=presspil").get_data(as_text=True)
    assert "Kun en tekst" not in admin.get("/team/notes?q=%25").get_data(as_text=True)                                  # % er ikke jokertegn
    admin.post(f"/team/notes/{nid}/edit", {"title": "Træning 12. nov", "note_date": "2026-11-12", "body": "Rettet af en anden"}, page=f"/team/notes/{nid}")
    v = admin.get(f"/team/notes/{nid}").get_data(as_text=True)
    assert "Rettet af en anden" in v and "sidst rettet af" in v
    # hold B kan hverken se, rette eller slette holdets noter
    switch(admin, team_id(app, "B"))
    assert "Træning 12. nov" not in admin.get("/team/notes").get_data(as_text=True)
    assert admin.get(f"/team/notes/{nid}").status_code == 404
    assert admin.post(f"/team/notes/{nid}/edit", {"body": "hack"}, page="/team/notes").status_code == 404
    assert admin.post(f"/team/notes/{nid}/delete", {}, page="/team/notes").status_code == 404
    assert sql(app, "SELECT body FROM team_notes WHERE id=?", nid)[0]["body"] == "Rettet af en anden"


def test_links_without_access_are_hidden_and_hold_tile_is_on_home(app, admin):
    make_team(admin, "A"); switch(admin, team_id(app, "A"))
    home = admin.get("/?hold=1").get_data(as_text=True)
    assert 'href="/team/"' in home and "Noter" in home
    assert 'href="/team/"' not in admin.get("/menu").get_data(as_text=True)


# ----------------------------------------------------------------------------- rollebaseret menu
def _menu(c, path="/menu"):
    return c.get(path).get_data(as_text=True)


def test_role_based_menus(world):
    app, admin, ca, cb, ta, tb = world
    tid = team_id(app, "Hold Alfa")
    # systemadministrator og klubadministrator lander på administration og ser ikke holdets menu
    for c, label in ((admin, "Administration"), (ca, "Klubadministration")):
        r = c.get("/")
        assert r.status_code == 302 and "/admin/" in r.headers["Location"]
        page = c.get("/admin/").get_data(as_text=True)
        nav = page.split('<nav class="side"')[1].split("</nav>")[0]
        assert label in nav and "Spillere" not in nav and "Teamoversigt" not in nav and "Beskeder" in nav
        assert "Spillere" in c.get("/?hold=1").get_data(as_text=True).split('<nav class="side"')[1].split("</nav>")[0]
    # træner: holdets menu, ingen administration eller assistent-invitation
    nav = ta.get("/").get_data(as_text=True).split('<nav class="side"')[1].split("</nav>")[0]
    assert "Spillere" in nav and "Motivation" in nav and "Administration" not in nav and "Assistenter" not in nav
    # chef-træner får «Mit hold» og «Assistenter»
    ca.post(f"/admin/teams/{tid}/head", {"head_user": [str(sql(app, "SELECT id FROM users WHERE username='tina'")[0]["id"])]}, page="/admin/teams")
    nav = ta.get("/").get_data(as_text=True).split('<nav class="side"')[1].split("</nav>")[0]
    assert "Mit hold" in nav and "Assistenter" in nav
    assert "Assistenter" in ta.get("/admin/invitations/").get_data(as_text=True)
    # assistent: ingen kampe, holdsætning, motivation, udviklingsdata, rapporter
    sql(app, "UPDATE users SET readonly=1 WHERE username='tina'")
    nav = ta.get("/").get_data(as_text=True).split('<nav class="side"')[1].split("</nav>")[0]
    assert "Evaluering" in nav and "Motivation" not in nav and "Udviklingsdata" not in nav and "Rapporter" not in nav and "Assistenter" not in nav


def test_assistant_locked_out_of_sensitive_sections(world):
    app, admin, ca, cb, ta, tb = world
    sql(app, "UPDATE users SET readonly=1 WHERE username='tina'")
    for path in ("/motivation/", "/devdata/", "/reports", "/kampe/", "/lineup/"):
        assert ta.get(path).status_code == 403, path
    assert ta.get("/eval").status_code == 200 and ta.get("/players/").status_code == 200


def test_note_edit_with_javascript_stays_on_the_edit_page(app, admin):
    """I-09: «Gem» i en note med JS bliver på redigeringssiden; uden JS går man til noten som før."""
    make_team(admin, "A"); switch(admin, team_id(app, "A"))
    admin.post("/team/notes/add", {"title": "Swap", "body": "Første"}, page="/team/notes/new")
    nid = sql(app, "SELECT id FROM team_notes WHERE title='Swap'")[0]["id"]
    pg = f"/team/notes/{nid}/edit"
    r = admin.post(pg, {"title": "Swap", "body": "Anden"}, page=pg, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 302 and r.headers["Location"].endswith(pg)
    r = admin.post(pg, {"title": "Swap", "body": "Tredje"}, page=pg)
    assert r.headers["Location"].endswith(f"/team/notes/{nid}")
    assert 'data-swap="#noteform"' in admin.get(pg).get_data(as_text=True)
