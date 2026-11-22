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


def test_team_focus_saved_shown_and_scoped(world):
    from helpers import add_player, player_id, score_all
    from app import model
    app, admin, ca, cb, ta, tb = world
    add_player(ta, "Anna Alfa")
    score_all(ta, 1, player_id(app, "Anna Alfa"), 3)
    c0 = model.CRITERIA[0]
    nm = f"{c0['skill']} som {c0['role'].lower()}"
    ta.post("/team/focus", {"pick": [nm, "opfundet"], "own": "Aflevering med indersiden"}, page="/team/focus")
    page = ta.get("/team/focus").get_data(as_text=True)
    assert nm in page and "Aflevering med indersiden" in page and "opfundet" not in page      # kun kendte forslag gemmes
    assert "<b>Holdets fokus</b>" in ta.get("/").get_data(as_text=True) and "Aflevering med indersiden" in ta.get("/").get_data(as_text=True)
    assert "Aflevering med indersiden" not in tb.get("/").get_data(as_text=True)               # andet hold ser det ikke
    rep = ta.get("/report/%d/foraeldre" % player_id(app, "Anna Alfa")).get_data(as_text=True)
    assert "Hele holdet træner på" in rep and "Aflevering med indersiden" in rep
    ta.post("/team/focus", {}, page="/team/focus")
    assert "<b>Holdets fokus</b>" not in ta.get("/").get_data(as_text=True)


def test_parent_reports_whole_team_and_motivation_history(world):
    from helpers import add_player, player_id
    app, admin, ca, cb, ta, tb = world
    add_player(ta, "Anna Alfa"); add_player(ta, "Bo Beta")
    add_player(tb, "Cille Gamma")
    html = ta.get("/reports/foraeldre").get_data(as_text=True)
    assert "Anna Alfas udvikling" in html and "Bo Betas udvikling" in html and "Cille" not in html
    pid = player_id(app, "Anna Alfa")
    sql(app, "INSERT INTO motivation_questions(team_id,qidx,cat,text) VALUES((SELECT team_id FROM players WHERE id=?),1,1,'Spørgsmål')", pid) if not sql(app, "SELECT 1 FROM motivation_questions WHERE team_id=(SELECT team_id FROM players WHERE id=?) AND qidx=1", pid) else None
    sql(app, "INSERT OR REPLACE INTO motivation_answers(player_id,qidx,score) VALUES(?,1,3)", pid)
    sql(app, "UPDATE motivation_log SET taken_on='2026-01-01' WHERE player_id=?", pid)
    sql(app, "UPDATE motivation_answers SET score=5 WHERE player_id=? AND qidx=1", pid)
    assert [r["score"] for r in sql(app, "SELECT score FROM motivation_log WHERE player_id=? ORDER BY taken_on", pid)] == [3, 5]


def test_reply_private_and_read_stats(world):
    app, admin, ca, cb, ta, tb = world
    mia = make_user(app, admin, "mia", "trainer", "Alfa Klub", ["U11 Alfa"])
    ca.post("/inbox/send", {"to": "club", "title": "Møde", "body": "Torsdag?"}, page="/inbox/")
    page = ca.get("/inbox/").get_data(as_text=True)
    assert "Læst af 0 af 2" in page                                   # tina + mia (afsenderen tæller ikke)
    ta.post("/inbox/read", {}, page="/inbox/")
    assert "Læst af 1 af 2" in ca.get("/inbox/").get_data(as_text=True)
    mid = sql(app, "SELECT id FROM messages")[0]["id"]
    assert ta.post(f"/inbox/{mid}/reply", {"body": "Jeg kan godt"}, page="/inbox/").status_code == 302
    assert "Jeg kan godt" in ca.get("/").get_data(as_text=True)         # afsenderen får svaret som ulæst
    for other in (mia, tb, cb):
        assert "Jeg kan godt" not in other.get("/inbox/").get_data(as_text=True)    # svaret er privat
    assert tb.post(f"/inbox/{mid}/reply", {"body": "x"}, page="/inbox/").status_code == 404
    rid = sql(app, "SELECT id FROM messages WHERE to_user_id IS NOT NULL")[0]["id"]
    assert ca.post(f"/inbox/{rid}/delete", {}, page="/inbox/").status_code == 403    # modtager sletter ikke andres private svar


def test_conversations_scoped_and_homework_on_parent_report(world):
    from helpers import add_player, player_id
    app, admin, ca, cb, ta, tb = world
    add_player(ta, "Anna Alfa")
    pid = player_id(app, "Anna Alfa")
    ta.post(f"/samtaler/{pid}/ny", {"held_on": "2026-11-20", "notes": "God snak", "agreements": "Øver mere", "homework": "Aflever mod væg"}, page=f"/samtaler/{pid}")
    assert "God snak" in ta.get(f"/samtaler/{pid}").get_data(as_text=True)
    assert tb.get(f"/samtaler/{pid}").status_code == 404                                       # andet hold
    assert tb.post(f"/samtaler/{pid}/ny", {"held_on": "2026-11-20", "notes": "x"}, page="/").status_code == 404
    assert "Aflever mod væg" in ta.get(f"/report/{pid}/foraeldre").get_data(as_text=True)
    assert "God snak" not in ta.get(f"/report/{pid}/foraeldre").get_data(as_text=True)         # noter vises ikke for forældre
    ta.post(f"/samtaler/{pid}/ny", {"held_on": "ugyldig", "notes": "y"}, page=f"/samtaler/{pid}")
    assert len(sql(app, "SELECT id FROM conversations")) == 1
