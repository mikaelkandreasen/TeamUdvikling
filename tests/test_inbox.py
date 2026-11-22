"""Indbakke: klub- og holdbeskeder, ulæst/læst, afgrænsning og e-mail."""
from helpers import team_id
from test_clubs_invites import make_user, mailapp, sql, world  # noqa: F401


def test_club_message_scope_read_and_rights(world):
    app, admin, ca, cb, ta, tb = world
    assert ta.post("/inbox/send", {"to": "club", "title": "x", "body": "y"}, page="/inbox/").status_code == 403
    assert ta.post("/inbox/send", {"to": "team", "title": "x", "body": "y"}, page="/inbox/").status_code == 403
    ca.post("/inbox/send", {"to": "club", "title": "Hej alle", "body": "Husk træning"}, page="/inbox/")
    assert "Husk træning" in ta.get("/").get_data(as_text=True) and "Nye beskeder" in ta.get("/").get_data(as_text=True)
    for other in (tb, cb):
        assert "Husk træning" not in other.get("/inbox/").get_data(as_text=True)           # anden klub ser intet
    assert "Nye beskeder" not in ca.get("/").get_data(as_text=True)                         # afsenderen har den læst
    ta.post("/inbox/read", {}, page="/inbox/")
    assert "Nye beskeder" not in ta.get("/").get_data(as_text=True)
    assert "Husk træning" in ta.get("/inbox/").get_data(as_text=True)                       # gemt i indbakken
    mid = sql(app, "SELECT id FROM messages")[0]["id"]
    assert tb.post(f"/inbox/{mid}/delete", {}, page="/inbox/").status_code == 404           # fremmed klub
    assert ta.post(f"/inbox/{mid}/delete", {}, page="/inbox/").status_code == 403           # modtager må ikke slette
    assert ca.post(f"/inbox/{mid}/delete", {}, page="/inbox/").status_code == 302


def test_head_coach_team_message_and_email(world):
    app, admin, ca, cb, ta, tb = world
    mia = make_user(app, admin, "mia", "trainer", "Alfa Klub", ["U11 Alfa"])
    sql(app, "UPDATE users SET email='tina@example.dk' WHERE username='tina'")
    sql(app, "UPDATE users SET email='mia@example.dk' WHERE username='mia'")
    sql(app, "UPDATE users SET email='ole@example.dk' WHERE username='ole'")
    sql(app, "UPDATE users SET email='kaja@example.dk' WHERE username='kaja'")
    tid = team_id(app, "U11 Alfa")
    uid = sql(app, "SELECT id FROM users WHERE username='tina'")[0]["id"]
    sql(app, "INSERT INTO team_heads(team_id,user_id) VALUES(?,?)", tid, uid)
    before = len(app.extensions.get("outbox", []))
    ta.post("/inbox/send", {"to": "team", "title": "Kamp lørdag", "body": "Mød kl. 9", "email": "1"}, page="/inbox/")
    sent = app.extensions["outbox"][before:]
    assert [m["to"] for m in sent] == ["mia@example.dk"]                                    # ikke afsenderen, ikke andre hold/klubber
    assert "Mød kl. 9" in mia.get("/").get_data(as_text=True)
    assert "Mød kl. 9" not in tb.get("/inbox/").get_data(as_text=True)
    assert "Mød kl. 9" not in ca.get("/inbox/").get_data(as_text=True)                     # klubadmin er ikke holdmedlem
    assert ta.post("/inbox/send", {"to": "club", "title": "x", "body": "y"}, page="/inbox/").status_code == 403


def test_sysadmin_message_reaches_everyone(world):
    app, admin, ca, cb, ta, tb = world
    sql(app, "UPDATE users SET email='tina@example.dk' WHERE username='tina'")
    sql(app, "UPDATE users SET email='ole@example.dk' WHERE username='ole'")
    before = len(app.extensions.get("outbox", []))
    admin.post("/inbox/send", {"to": "all", "title": "Vedligehold", "body": "Nede i aften", "email": "1"}, page="/inbox/")
    for c in (ca, cb, ta, tb):
        assert "Nede i aften" in c.get("/").get_data(as_text=True)
    assert sorted(m["to"] for m in app.extensions["outbox"][before:]) == ["ole@example.dk", "tina@example.dk"]
    assert ta.post("/inbox/send", {"to": "all", "title": "x", "body": "y"}, page="/inbox/").status_code == 403
    assert ca.post("/inbox/send", {"to": "all", "title": "x", "body": "y"}, page="/inbox/").status_code == 403
    mid = sql(app, "SELECT id FROM messages")[0]["id"]
    assert ca.post(f"/inbox/{mid}/delete", {}, page="/inbox/").status_code == 403
    assert admin.post(f"/inbox/{mid}/delete", {}, page="/inbox/").status_code == 302
