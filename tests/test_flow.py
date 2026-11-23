import io
import re

import pytest

from app import model
from helpers import add_player, make_team, make_trainer, player_id, score_all


@pytest.fixture
def team(app, admin):
    make_team(admin, "Pigehold")
    return admin


PAGES = ["/?hold=1", "/m?hold=1", "/menu", "/criteria", "/players/", "/players/new", "/eval", "/eval/1", "/eval/4", "/overview", "/overview/2",
         "/development", "/development/position", "/development/position?type=sekundaer&pos=Kant", "/areas",
         "/motivation/", "/motivation/questions", "/motivation/tablet", "/devdata/", "/reports", "/reports/all",
         "/account", "/admin/", "/admin/teams", "/admin/users", "/admin/settings", "/admin/audit", "/admin/export.xlsx"]


def test_all_pages_render_with_empty_team(team):
    for path in PAGES:
        r = team.get(path, headers={"User-Agent": "Desktop"})
        assert r.status_code == 200, (path, r.status_code)


def test_all_pages_render_with_data(app, team):
    names = [("Anna Alfa", "2016-01-15", "Angreb", "Kant"), ("Bea Bravo", "2016-05-02", "Kant", ""), ("Cille Charlie", "2016-08-20", "Midtbane", "Forsvar"),
             ("Dora Delta", "2016-11-30", "Målmand", ""), ("Eva Echo", "2016-12-31", "Allround", "Kant")]
    for n, b, p, p2 in names:
        add_player(team, n, b, p, p2)
    t2 = make_trainer(app, team, "t2", ["Pigehold"])
    for i, (n, *_r) in enumerate(names):
        pid = player_id(app, n)
        for rnd in (1, 2):
            score_all(team, rnd, pid, 2 + i % 3 + rnd - 1)
            score_all(t2, rnd, pid, 3)
    for path in PAGES + [f"/profile/{player_id(app, 'Anna Alfa')}", f"/report/{player_id(app, 'Anna Alfa')}",
                         f"/motivation/report/{player_id(app, 'Anna Alfa')}", f"/devdata/{player_id(app, 'Anna Alfa')}",
                         f"/eval/1/{player_id(app, 'Anna Alfa')}", f"/motivation/tablet/{player_id(app, 'Anna Alfa')}",
                         f"/players/{player_id(app, 'Anna Alfa')}/edit", f"/players/{player_id(app, 'Anna Alfa')}/export.json"]:
        r = team.get(path, headers={"User-Agent": "Desktop"})
        assert r.status_code == 200, (path, r.status_code)
    html = team.get("/report/%d" % player_id(app, "Anna Alfa")).get_data(as_text=True)
    assert "<svg" in html and "Boldholder" in html and "Relativ alder" in html


def test_mobile_redirect_and_viewport(team):
    r = team.get("/?hold=1", headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148"})
    assert r.status_code == 302 and "/m" in r.headers["Location"]
    html = team.get("/m?hold=1").get_data(as_text=True)
    assert 'name="viewport" content="width=device-width, initial-scale=1' in html and "tabbar" in html


def test_evaluation_roundtrip_and_calculation(app, team):
    add_player(team, "Anna Alfa")
    pid = player_id(app, "Anna Alfa")
    data = {f"c{i}": "" for i in range(24)}
    for i in range(6):
        data[f"c{i}"] = "4"          # boldholder = 4
    for i in range(6, 12):
        data[f"c{i}"] = "2"          # medspiller = 2
    team.post(f"/eval/1/{pid}", data, page=f"/eval/1/{pid}")
    from app import db
    con = db.connect(app.config["DATABASE"])
    res = model.load_rounds(con, con.execute("SELECT team_id FROM players").fetchone()[0])[1][pid]
    con.close()
    assert res["roles"][:3] == [4, 2, None] and res["samlet"] == 3 and res["enighed"] is None
    # ugyldig score ignoreres, tomt felt sletter
    data = {f"c{i}": "9" for i in range(24)}
    team.post(f"/eval/1/{pid}", data, page=f"/eval/1/{pid}")
    con = db.connect(app.config["DATABASE"])
    assert con.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0] == 0
    con.close()


def test_devdata_relative_age_and_attendance(app, team):
    for n, b in [("Q1 pige", "2016-02-10"), ("Q1 pige2", "2016-03-01"), ("Q4 pige", "2016-11-11")]:
        add_player(team, n, b)
    form = {"trainings_total": "20", "matches_total": "10"}
    for n, tr, ma in [("Q1 pige", 20, 10), ("Q1 pige2", 18, 8), ("Q4 pige", 10, 4)]:
        pid = player_id(app, n)
        form.update({f"trainings_{pid}": str(tr), f"matches_{pid}": str(ma), f"t1_{pid}": "5", f"m1_{pid}": "3"})
    team.post("/devdata/", form, page="/devdata/")
    html = team.get("/devdata/").get_data(as_text=True)
    assert "100%" in html and "50%" in html and "Overvægt af tidligt fødte" in html      # 2 af 3 i 1. halvår = 67 %
    rep = team.get("/report/%d" % player_id(app, "Q4 pige")).get_data(as_text=True)
    assert "relativt yngst" in rep and "Q4" in rep


def test_motivation_matrix_report_and_extra_questions(app, team):
    add_player(team, "Anna Alfa")
    add_player(team, "Bea Bravo")
    a, b = player_id(app, "Anna Alfa"), player_id(app, "Bea Bravo")
    # tag en ledig plads i brug (spørgsmål 4 i kategori 1)
    form = {f"q_{i}": "" for i in range(22)}
    form.update({"title_0": "Hvorfor går jeg til fodbold?", "title_1": "Ønsker", "title_2": "Ekstra",
                 "q_0": "Sjovt", "q_1": "Venner", "q_4": "Mit eget spørgsmål", "q_8": "Mere spil", "q_9": "Nye tricks"})
    team.post("/motivation/questions", form, page="/motivation/questions")
    ans = {f"a_{a}_0": "5", f"a_{a}_1": "3", f"a_{a}_4": "4", f"a_{b}_0": "1", f"a_{a}_8": "2", f"a_{a}_9": "5"}
    team.post("/motivation/", ans, page="/motivation/")
    rep = team.get(f"/motivation/report/{a}").get_data(as_text=True)
    assert "Mit eget spørgsmål" in rep and "Største drivkraft:</b> Sjovt" in rep and "Største træningsønske:</b> Nye tricks" in rep
    # tablet-visning gemmer svar
    team.post(f"/motivation/tablet/{b}", {"q1": "4", "q9": "3"}, page=f"/motivation/tablet/{b}")
    assert "Tak for dine svar" in team.get("/motivation/tablet").get_data(as_text=True)


def test_csrf_required_on_posts(team):
    r = team.c.post("/players/new", data={"name": "X"})
    assert r.status_code == 400


def test_player_validation_and_admin_delete_gdpr(app, team):
    r = add_player(team, "Fejl", birth="ikke-en-dato")
    assert "Ugyldig dato" in r.get_data(as_text=True)
    add_player(team, "Anna Alfa")
    pid = player_id(app, "Anna Alfa")
    team.post(f"/players/{pid}/delete", {}, page=f"/players/{pid}/edit")           # uden bekræftelse
    assert player_id(app, "Anna Alfa") == pid
    j = team.get(f"/players/{pid}/export.json")
    assert j.status_code == 200 and "Anna Alfa" in j.get_data(as_text=True)
    team.post(f"/players/{pid}/delete", {"confirm": "ja"}, page=f"/players/{pid}/edit")
    with pytest.raises(TypeError):
        player_id(app, "Anna Alfa")


def test_trainer_cannot_delete_or_export_player(app, team):
    add_player(team, "Anna Alfa")
    pid = player_id(app, "Anna Alfa")
    t = make_trainer(app, team, "tr", ["Pigehold"])
    assert t.get(f"/players/{pid}/export.json").status_code == 403
    assert t.post(f"/players/{pid}/delete", {"confirm": "ja"}, page="/players/").status_code == 403


def test_excel_export_has_only_active_team(app, team):
    from openpyxl import load_workbook
    make_team(team, "U13 drenge")
    add_player(team, "Anna Alfa")
    wb = load_workbook(io.BytesIO(team.get("/admin/export.xlsx").data))
    assert {"Spillere", "Evalueringer", "Teamoversigt", "Motivation", "Udviklingsdata"} <= set(wb.sheetnames)
    assert [r[1].value for r in wb["Spillere"].iter_rows(min_row=2)] == ["Anna Alfa"]


def test_backup_download_and_auto_backup(app, team, tmp_path):
    r = team.post("/admin/backup", {}, page="/admin/")
    assert r.status_code == 200 and r.data[:15] == b"SQLite format 3"
    import os
    assert os.listdir(app.config["BACKUP_DIR"])


def test_no_inline_scripts_or_handlers(team):
    for path in ("/?hold=1", "/reports", "/players/"):
        html = team.get(path).get_data(as_text=True)
        assert "onclick=" not in html and "<script>" not in html


def test_eval_save_with_js_stays_on_player_and_without_js_goes_to_list(app, team):
    from helpers import add_player
    add_player(team, "Anna Alfa")
    pid = player_id(app, "Anna Alfa")
    data = {"c0": "3", "go": "stay"}
    r = team.post(f"/eval/1/{pid}", data, page=f"/eval/1/{pid}")
    assert r.status_code == 302 and r.headers["Location"].endswith("/eval/1")                      # uden JavaScript: tilbage til listen
    r = team.post(f"/eval/1/{pid}", data, page=f"/eval/1/{pid}", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/eval/1/{pid}")               # med JavaScript: bliv på spilleren
    page = team.get(f"/eval/1/{pid}").get_data(as_text=True)
    assert 'data-swap="#evalform"' in page and 'name="go" value="next"' not in page or "data-noswap" in page
