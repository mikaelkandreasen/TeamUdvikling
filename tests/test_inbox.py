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


def test_matches_minutes_white_spots_and_scoping(world):
    from helpers import add_player, player_id
    app, admin, ca, cb, ta, tb = world
    for n in ("Anna Alfa", "Bo Beta", "Cille Gamma"):
        add_player(ta, n)
    a, b, c = (player_id(app, n) for n in ("Anna Alfa", "Bo Beta", "Cille Gamma"))
    r = ta.post("/kampe/ny", {"day": "2026-11-01", "opponent": "Rivalerne", "game_type": "8v8", "formation": "3-3-1", "periods": "2", "period_min": "10"}, page="/kampe/")
    mid = sql(app, "SELECT id FROM matches")[0]["id"]
    assert r.status_code == 302
    # periode 0: Anna i mål, Bo angreb. periode 1: Bo i mål, Anna angreb. Cille aldrig på banen
    data = {"p0s0": a, "p0s7": b, "p1s0": b, "p1s7": a}
    assert ta.post(f"/kampe/{mid}", data, page=f"/kampe/{mid}").status_code == 302
    page = ta.get(f"/kampe/{mid}").get_data(as_text=True)
    assert "Anna Alfa: <b>20</b> min" in page and "Cille Gamma: <b>0</b> min" in page
    ov = ta.get("/kampe/overblik").get_data(as_text=True)
    from app import db as appdb
    from app.matches import overview_data
    with app.app_context():
        d = overview_data(appdb.get_db(), sql(app, "SELECT team_id FROM matches")[0]["team_id"], [dict(r) for r in sql(app, "SELECT * FROM players")])
    by = {s["p"]["name"]: s for s in d["rows"]}
    assert by["Anna Alfa"]["by"]["GK"] == 10 and by["Anna Alfa"]["by"]["ATT"] == 10 and by["Anna Alfa"]["total"] == 20
    assert d["used"] == ["GK", "ATT"] and by["Anna Alfa"]["missing"] == [] and by["Cille Gamma"]["missing"] == ["Målmand", "Angreb"]
    assert by["Cille Gamma"]["low"] and not by["Anna Alfa"]["low"]
    assert "mangler" in ov and "Cille Gamma" in ov
    # fejl: samme spiller to gange i en periode / spiller fra andet hold
    assert "to gange" in ta.post(f"/kampe/{mid}", {"p0s0": a, "p0s1": a}, page=f"/kampe/{mid}").get_data(as_text=True)
    add_player(tb, "Dan Delta")
    assert ta.post(f"/kampe/{mid}", {"p0s0": player_id(app, "Dan Delta")}, page=f"/kampe/{mid}").status_code == 400
    # isolation
    assert tb.get(f"/kampe/{mid}").status_code == 404 and tb.post(f"/kampe/{mid}/slet", {}, page="/kampe/").status_code == 404
    assert "Rivalerne" not in tb.get("/kampe/").get_data(as_text=True)
    # perioder skæres ned fjerner overskydende periode
    ta.post(f"/kampe/{mid}/meta", {"day": "2026-11-01", "opponent": "Rivalerne", "periods": "1", "period_min": "10"}, page=f"/kampe/{mid}")
    assert len(sql(app, "SELECT * FROM match_slots")) == 2


def test_assistant_can_mark_read_but_not_send(world):
    app, admin, ca, cb, ta, tb = world
    ca.post("/inbox/send", {"to": "club", "title": "Info", "body": "Læs mig"}, page="/inbox/")
    sql(app, "UPDATE users SET readonly=1 WHERE username='tina'")
    assert "Læs mig" in ta.get("/").get_data(as_text=True)
    assert ta.post("/inbox/read", {}, page="/inbox/").status_code == 302
    assert "Nye beskeder" not in ta.get("/").get_data(as_text=True)
    assert ta.post("/inbox/send", {"to": "team", "title": "x", "body": "y"}, page="/inbox/").status_code == 403


def test_assistant_evaluates_but_counts_only_if_head_coach_includes(world):
    from helpers import add_player, player_id, score_all
    from app import db as appdb, model
    app, admin, ca, cb, ta, tb = world
    mia = make_user(app, admin, "mia", "trainer", "Alfa Klub", ["U11 Alfa"])
    tid = team_id(app, "U11 Alfa")
    add_player(mia, "Anna Alfa")
    pid = player_id(app, "Anna Alfa")
    sql(app, "UPDATE users SET readonly=1 WHERE username='tina'")                     # tina er assistent
    sql(app, "INSERT INTO team_heads(team_id,user_id) VALUES(?,(SELECT id FROM users WHERE username='mia'))", tid)
    score_all(mia, 1, pid, 4)
    score_all(ta, 1, pid, 2)                                                          # assistentens evaluering gemmes
    assert len(sql(app, "SELECT * FROM evaluations WHERE trainer_id=(SELECT id FROM users WHERE username='tina')")) == 24

    def samlet(db_tid=tid):
        con = appdb.connect(app.config["DATABASE"])
        v = model.load_rounds(con, db_tid)[1][pid]["samlet"]
        con.close()
        return v
    assert samlet() == 4                                                               # standard: assistenten tæller ikke
    assert ta.post("/admin/evaluations", {"action": "assist", "round": "1", "inc": str(sql(app, "SELECT id FROM users WHERE username='tina'")[0]["id"])}, page="/").status_code == 403
    uid = sql(app, "SELECT id FROM users WHERE username='tina'")[0]["id"]
    assert mia.post("/admin/evaluations", {"action": "assist", "round": "1", "inc": str(uid)}, page="/admin/evaluations").status_code == 302
    assert samlet() == 3                                                               # medtaget: (4 + 2) / 2
    assert "medtag" in mia.get("/admin/evaluations").get_data(as_text=True)
    mia.post("/admin/evaluations", {"action": "assist", "round": "1"}, page="/admin/evaluations")
    assert samlet() == 4


ICS = """BEGIN:VCALENDAR\r
BEGIN:VEVENT\r
UID:a1@x\r
DTSTART:{d1}T080000Z\r
SUMMARY:U11 Piger: Alfa IF - Beta\\, BK\r
LOCATION:Bane 3\\, Beta\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:a2@x\r
DTSTART;VALUE=DATE:{d2}\r
SUMMARY:Gamma vs Alfa IF\r
STATUS:CANCELLED\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:a3@x\r
DTSTART:20200101T100000Z\r
SUMMARY:Gammel kamp\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:a4@x\r
DTSTART;TZID=Europe/Copenhagen:{d1}T100000\r
SUMMARY:Delta -\r
 Alfa IF\r
END:VEVENT\r
END:VCALENDAR\r
"""


def test_guess_opponent():
    from app.matches import guess_opponent
    assert guess_opponent("U11 Piger: Alfa IF - Beta, BK", ["U11 Alfa", "Alfa IF", "Alfa"]) == ("Beta, BK", True)
    assert guess_opponent("Gamma vs Alfa IF", ["Alfa"]) == ("Gamma", True)
    assert guess_opponent("Træning", ["Alfa"]) == ("Træning", False)


def test_match_suggestions_import_no_duplicates(world, monkeypatch):
    import datetime
    from app import ical
    app, admin, ca, cb, ta, tb = world
    d1 = (datetime.date.today() + datetime.timedelta(days=20)).strftime("%Y%m%d")
    d2 = (datetime.date.today() + datetime.timedelta(days=21)).strftime("%Y%m%d")
    monkeypatch.setattr(ical, "fetch", lambda url: ICS.format(d1=d1, d2=d2))
    tid = team_id(app, "U11 Alfa")
    assert ta.get("/kampe/forslag").status_code == 302                                       # intet link endnu
    sql(app, "INSERT INTO settings(key,value) VALUES(?,?)", f"t{tid}:ical_url", "https://x.example/a.ics")
    page = ta.get("/kampe/forslag").get_data(as_text=True)
    assert "Beta, BK" in page and "Gammel kamp" not in page and "Gamma" not in page          # fortid og aflyst udeladt
    day = f"{d1[:4]}-{d1[4:6]}-{d1[6:]}"
    ta.post("/kampe/importer", {"pick": ["0"], "day0": day, "time0": "10:00", "loc0": "Bane 3", "opp0": "Beta, BK", "uid0": "a1@x"}, page="/kampe/forslag")
    m = sql(app, "SELECT * FROM matches WHERE team_id=?", tid)
    assert len(m) == 1 and m[0]["opponent"] == "Beta, BK" and m[0]["note"] == "kl. 10:00 · Bane 3" and m[0]["ical_uid"] == "a1@x"
    ta.post("/kampe/importer", {"pick": ["0"], "day0": day, "opp0": "x", "uid0": "a1@x"}, page="/kampe/forslag")
    assert len(sql(app, "SELECT * FROM matches WHERE team_id=?", tid)) == 1                  # samme uid oprettes ikke to gange
    assert "Beta, BK" not in ta.get("/kampe/forslag").get_data(as_text=True)                 # oprettede vises ikke igen
    assert sql(app, "SELECT COUNT(*) n FROM matches WHERE team_id<>?", tid)[0]["n"] == 0     # intet landede på andre hold
    assert tb.get("/kampe/forslag").status_code == 302                                       # andet hold: intet link, intet at se


def test_suggest_algorithm_prioritises_white_spots_and_balances_time():
    from app import suggest
    slots = [dict(i=0, tag="Målmand"), dict(i=1, tag="Forsvar"), dict(i=2, tag="Midtbane"), dict(i=3, tag="Angreb")]
    grp = {"Målmand": "GK", "Forsvar": "DEF", "Midtbane": "MID", "Angreb": "ATT"}.get
    ids = [1, 2, 3, 4, 5]
    hist = {1: {"DEF": 48, "MID": 24}, 2: {"DEF": 24, "ATT": 24}, 3: {"MID": 48}, 4: {"ATT": 48, "GK": 12}, 5: {}}
    assign, filled = suggest.suggest(slots, grp, ids, hist, 4, 12)
    per_player = {}
    for (per, i), pid in assign.items():
        per_player[pid] = per_player.get(pid, 0) + 1
    assert len(assign) == 16 and max(per_player.values()) - min(per_player.values()) <= 1      # spilletid jævnt (5 spillere på 4 pladser)
    for per in range(4):
        assert len({pid for (p, i), pid in assign.items() if p == per}) == 4                    # ingen spiller to steder i samme periode
    assert (1, "ATT") in filled and (3, "DEF") in filled                                        # hvide pletter udfyldes
    a2, _ = suggest.suggest(slots, grp, ids, hist, 4, 12, absent={5}, use_gk=False)
    assert 5 not in a2.values() and all(i != 0 for (_p, i) in a2)                               # fraværende og målmandsplads udeladt


def test_suggest_route_does_not_save_until_gem(world):
    app, admin, ca, cb, ta, tb = world
    tid = team_id(app, "U11 Alfa")
    for n in ("Anna", "Bo", "Cille", "Dina", "Ella", "Fie", "Gry", "Hanne"):
        sql(app, "INSERT INTO players(team_id,name,active) VALUES(?,?,1)", tid, n)
    ta.post("/kampe/ny", {"day": "2030-05-01", "opponent": "X"}, page="/kampe/")
    mid = sql(app, "SELECT id FROM matches WHERE team_id=?", tid)[0]["id"]
    r = ta.post(f"/kampe/{mid}", {"action": "suggest", "use_gk": "1"}, page=f"/kampe/{mid}")
    assert r.status_code == 200 and "Forslag lavet" in r.get_data(as_text=True)
    assert sql(app, "SELECT COUNT(*) n FROM match_slots WHERE match_id=?", mid)[0]["n"] == 0
    other = sql(app, "SELECT id FROM players WHERE team_id=? LIMIT 1", tid)[0]["id"]
    assert tb.post(f"/kampe/{mid}", {"action": "suggest"}, page="/kampe/").status_code in (302, 403, 404)


def test_partial_update_hooks_exist_and_pages_still_work_without_js(world):
    app, admin, ca, cb, ta, tb = world
    ca.post("/inbox/send", {"to": "club", "title": "Hej", "body": "Tekst"}, page="/inbox/")
    page = ca.get("/inbox/").get_data(as_text=True)
    assert 'id="inbox-main"' in page and 'id="inbox-badge"' in page and 'data-swap="#inbox-main,#inbox-badge"' in page
    assert "onsubmit" not in page and "<script>" not in page                                  # CSP: ingen indlejret JS
    js = ca.get("/static/app.js").get_data(as_text=True)
    assert "form[data-swap]" in js
    # almindelig POST (uden JS) virker som før: redirect tilbage til indbakken
    assert ta.post("/inbox/read", {}, page="/inbox/").status_code == 302
