import pytest

from conftest import Client
from helpers import add_player, make_team, make_trainer, player_id, score_all, switch, team_id


@pytest.fixture
def two_teams(app, admin):
    make_team(admin, "Pigehold")
    make_team(admin, "U13 drenge")
    return admin


def test_trainer_only_sees_assigned_team(app, two_teams):
    admin = two_teams
    add_player(admin, "Anna Alfa")                      # admin starter på første hold alfabetisk: "Pigehold"
    switch(admin, team_id(app, "U13 drenge"))
    add_player(admin, "Bo Bravo")
    t = make_trainer(app, admin, "trainer11", ["Pigehold"])
    html = t.get("/players/").get_data(as_text=True)
    assert "Anna Alfa" in html and "Bo Bravo" not in html
    # direkte adgang til den andres spiller giver 404
    other = player_id(app, "Bo Bravo")
    assert t.get(f"/players/{other}/edit").status_code == 404
    assert t.get(f"/profile/{other}").status_code == 404
    assert t.get(f"/eval/1/{other}").status_code == 404
    assert t.get(f"/report/{other}").status_code == 404
    assert t.get(f"/devdata/{other}").status_code == 404
    assert t.get(f"/motivation/tablet/{other}").status_code == 404
    assert score_all(t, 1, other, 3, page="/players/").status_code == 404      # gyldigt CSRF-token, men fremmed spiller


def test_trainer_cannot_switch_to_unassigned_team(app, two_teams):
    t = make_trainer(app, two_teams, "trainer11", ["Pigehold"])
    assert switch(t, team_id(app, "U13 drenge")).status_code == 403
    assert "Pigehold" in t.get("/players/").get_data(as_text=True)


def test_trainer_with_two_teams_can_switch(app, two_teams):
    admin = two_teams
    add_player(admin, "Anna Alfa")
    switch(admin, team_id(app, "U13 drenge"))
    add_player(admin, "Bo Bravo")
    t = make_trainer(app, admin, "begge", ["Pigehold", "U13 drenge"])
    assert "Anna Alfa" in t.get("/players/").get_data(as_text=True)
    assert switch(t, team_id(app, "U13 drenge")).status_code == 302
    html = t.get("/players/").get_data(as_text=True)
    assert "Bo Bravo" in html and "Anna Alfa" not in html


def test_trainer_has_no_admin_access(app, two_teams):
    t = make_trainer(app, two_teams, "trainer11", ["Pigehold"])
    for path in ("/admin/", "/admin/users", "/admin/teams", "/admin/export.xlsx", "/admin/audit"):
        assert t.get(path).status_code == 403, path
    assert t.post("/admin/teams", {"name": "Hack"}, page="/").status_code == 403


def test_trainer_without_team_sees_nothing(app, two_teams):
    t = make_trainer(app, two_teams, "uden", [])
    r = t.get("/players/")
    assert r.status_code == 302 and "/no-team" in r.headers["Location"]


def test_settings_and_questions_are_per_team(app, two_teams):
    admin = two_teams
    admin.post("/admin/settings", {"label_1": "Efterår 11"}, page="/admin/settings")
    switch(admin, team_id(app, "U13 drenge"))
    assert "Efterår 11" not in admin.get("/eval").get_data(as_text=True)
    form = {f"q_{i}": "" for i in range(22)}
    form.update({"title_0": "Drenge-titel", "q_0": "Kun for drenge", "title_1": "B", "title_2": "C"})
    admin.post("/motivation/questions", form, page="/motivation/questions")
    switch(admin, team_id(app, "Pigehold"))
    html = admin.get("/motivation/questions").get_data(as_text=True)
    assert "Hvorfor går jeg til fodbold?" in html and "Kun for drenge" not in html


def test_delete_team_removes_all_its_data(app, two_teams):
    admin = two_teams
    add_player(admin, "Anna Alfa")
    pid = player_id(app, "Anna Alfa")
    score_all(admin, 1, pid, 4)
    tid = team_id(app, "Pigehold")
    r = admin.post(f"/admin/teams/{tid}/delete", {"confirm": "forkert"}, page="/admin/teams")
    assert "bekræft" in admin.get("/admin/teams").get_data(as_text=True) or r.status_code == 302
    admin.post(f"/admin/teams/{tid}/delete", {"confirm": "Pigehold"}, page="/admin/teams")
    from app import db
    con = db.connect(app.config["DATABASE"])
    assert con.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0] == 0
    con.close()


def test_two_trainers_scores_are_averaged_per_team(app, two_teams):
    admin = two_teams
    add_player(admin, "Anna Alfa")
    pid = player_id(app, "Anna Alfa")
    t1 = make_trainer(app, admin, "t1", ["Pigehold"])
    t2 = make_trainer(app, admin, "t2", ["Pigehold"])
    score_all(t1, 1, pid, 2)
    score_all(t2, 1, pid, 5)
    html = t1.get("/overview/1").get_data(as_text=True)
    assert "3,5" in html                         # samlet = gennemsnit af trænerne
    assert "Stor forskel" in html                # enighed = 3 → stor forskel


def test_lineups_and_photos_are_isolated_between_teams(app, two_teams):
    import io
    from PIL import Image
    admin = two_teams
    add_player(admin, "Anna Alfa")
    switch(admin, team_id(app, "U13 drenge"))
    add_player(admin, "Bo Bravo")
    bo = player_id(app, "Bo Bravo")
    buf = io.BytesIO()
    Image.new("RGB", (300, 300), "blue").save(buf, "JPEG")
    admin.c.post(f"/players/{bo}/photo", data={"csrf_token": admin.token(f"/players/{bo}/edit"), "consent": "ja",
                                              "photo": (io.BytesIO(buf.getvalue()), "x.jpg")}, content_type="multipart/form-data")
    r = admin.post("/lineup/new", {"game_type": "3v3", "formation": "1-2", "name": "Hemmeligt"}, page="/lineup/")
    lid = int(r.headers["Location"].rsplit("/", 1)[1])
    t = make_trainer(app, admin, "trainer11", ["Pigehold"])
    assert t.get(f"/players/{bo}/photo.jpg").status_code == 404
    assert t.get(f"/players/{bo}/photo.jpg?s=full").status_code == 404
    assert t.get(f"/lineup/{lid}").status_code == 404
    for path in (f"/lineup/{lid}", f"/lineup/{lid}/meta", f"/lineup/{lid}/ideal", f"/lineup/{lid}/delete"):
        assert t.post(path, {"action": "save", "confirm": "ja"}, page="/lineup/").status_code == 404
    assert "Hemmeligt" not in t.get("/lineup/").get_data(as_text=True)
    assert "Bo Bravo" not in t.get("/development/position").get_data(as_text=True)
    from app import db
    con = db.connect(app.config["DATABASE"])
    assert con.execute("SELECT COUNT(*) FROM lineups").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM player_photos").fetchone()[0] == 1
    con.close()


def test_parent_report_and_mascot_image(app, two_teams):
    import io
    from PIL import Image
    admin = two_teams
    add_player(admin, "Anna Alfa")
    pid = player_id(app, "Anna Alfa")
    admin.post("/team/settings", {"game_type": "8v8", "subs": "3", "slogan": "Sammen er vi stærkest", "mascot_name": "Bamse"}, page="/team/settings")
    r = admin.get(f"/report/{pid}/foraeldre")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Sammen er vi stærkest" in html and "Anna Alfas udvikling" in html and "mascot-img" not in html.replace(".mascot-img", "")
    buf = io.BytesIO(); Image.new("RGB", (200, 120), (200, 30, 30)).save(buf, "PNG"); buf.seek(0)
    up = admin.c.post("/team/mascot-image/save", data={"csrf_token": admin.token("/team/settings"), "image": (buf, "m.png")}, content_type="multipart/form-data")
    assert up.status_code == 302 and admin.get("/team/mascot-image").mimetype == "image/jpeg"
    assert 'class="mascot-img"' in admin.get(f"/report/{pid}/foraeldre").get_data(as_text=True)
    # isolation: trænere på andet hold ser hverken rapport eller billede
    t = make_trainer(app, admin, "trainer13", ["U13 drenge"])
    assert t.get(f"/report/{pid}/foraeldre").status_code == 404
    assert t.get("/team/mascot-image").status_code == 404
    assert t.c.post("/team/mascot-image/delete", data={"csrf_token": t.token("/")}).status_code in (302, 403)
    assert admin.get("/team/mascot-image").status_code == 200

