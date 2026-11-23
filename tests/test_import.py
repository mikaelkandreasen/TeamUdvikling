import io
import json
import os
import re

import pytest

from conftest import Client
from helpers import make_team, make_trainer, player_id, team_id

CSV = ("Hold;Sæson;Navn;Fødselsdato;Trøjenr;Position;Fod;Aktiv\n"
       "Pigehold;2026/27;Anna Alfa;10-03-2016;7;midtbane;Højre;ja\n"
       "Pigehold;2026/27;Bella Beta;2016-05-02;9;Rumskib;Venstre;nej\n"
       "U12 piger;;Clara Gamma;;;;;\n"
       ";;;;;;;\n"
       "Pigehold;;;2016-01-01;;;;\n"
       "Pigehold;;Anna Alfa;10-03-2016;;;;\n")


def upload(admin, data, name="spillere.csv"):
    return admin.c.post("/admin/import", data={"csrf_token": admin.token("/admin/import"), "file": (io.BytesIO(data), name)},
                        content_type="multipart/form-data")


def commit(admin, html):
    token = re.search(r'name="token" value="([^"]+)"', html).group(1)
    return admin.post("/admin/import/commit", {"token": token, "confirm": "ja"}, page="/admin/import")


def rows(app, sql, *a):
    from app import db
    con = db.connect(app.config["DATABASE"])
    out = con.execute(sql, a).fetchall()
    con.close()
    return out


def test_preview_saves_nothing_then_commit_creates_teams_and_players(app, admin):
    r = upload(admin, CSV.encode("utf-8-sig"))
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Forhåndsvisning" in html
    assert "U12 piger" in html and "dublet i filen" in html and "navn mangler" in html
    assert rows(app, "SELECT COUNT(*) c FROM players")[0]["c"] == 0          # intet gemt før bekræftelse
    commit(admin, html)
    names = [r["name"] for r in rows(app, "SELECT name FROM players ORDER BY name")]
    assert names == ["Anna Alfa", "Bella Beta", "Clara Gamma"]
    anna = rows(app, "SELECT * FROM players WHERE name='Anna Alfa'")[0]
    assert anna["birth_date"] == "2016-03-10" and anna["position"] == "Midtbane" and anna["foot"] == "Højre" and anna["active"] == 1
    bella = rows(app, "SELECT * FROM players WHERE name='Bella Beta'")[0]
    assert bella["position"] is None and bella["active"] == 0                  # ukendt position ignoreres
    assert {r["name"] for r in rows(app, "SELECT name FROM teams")} == {"Pigehold", "U12 piger"}
    assert rows(app, "SELECT season FROM teams WHERE name='Pigehold'")[0]["season"] == "2026/27"


def test_reimport_updates_instead_of_duplicating(app, admin):
    commit(admin, upload(admin, CSV.encode()).get_data(as_text=True))
    again = "Hold;Navn;Fødselsdato;Noter\nPigehold;Anna Alfa;2016-03-10;Ny note\n"
    html = upload(admin, again.encode()).get_data(as_text=True)
    assert "Opdateres" in html
    commit(admin, html)
    assert rows(app, "SELECT COUNT(*) c FROM players WHERE name='Anna Alfa'")[0]["c"] == 1
    a = rows(app, "SELECT * FROM players WHERE name='Anna Alfa'")[0]
    assert a["notes"] == "Ny note" and a["position"] == "Midtbane"            # tomme felter overskriver ikke


def test_without_hold_column_uses_active_team(app, admin):
    make_team(admin, "Pigehold")
    html = upload(admin, b"Navn\nDagmar Delta\n").get_data(as_text=True)
    commit(admin, html)
    r = rows(app, "SELECT t.name tn FROM players p JOIN teams t ON t.id=p.team_id WHERE p.name='Dagmar Delta'")
    assert r[0]["tn"] == "Pigehold"


def test_xlsx_upload_and_formulas_never_executed(app, admin):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    ws.append(["Hold", "Navn", "Fødselsdato", "Noter"])
    ws.append(["Pigehold", "Emma Epsilon", "2016-02-14", '=HYPERLINK("http://evil","x")'])
    buf = io.BytesIO(); wb.save(buf)
    commit(admin, upload(admin, buf.getvalue(), "x.xlsx").get_data(as_text=True))
    n = rows(app, "SELECT notes FROM players WHERE name='Emma Epsilon'")[0]["notes"]
    assert n in (None, '=HYPERLINK("http://evil","x")')                         # aldrig udført: ingen cachet værdi → tom, eller ren tekst
    assert rows(app, "SELECT COUNT(*) c FROM players")[0]["c"] == 1


@pytest.mark.parametrize("name,data,msg", [
    ("x.pdf", b"%PDF-1.4 hej", "xlsx"),
    ("x.xlsx", b"PK\x03\x04ikke-en-zip", "Excel"),
    ("x.csv", b"Foo;Bar\n1;2\n", "Navn"),
    ("x.csv", b"", "tom"),
])
def test_bad_files_rejected_gracefully(app, admin, name, data, msg):
    r = admin.c.post("/admin/import", data={"csrf_token": admin.token("/admin/import"), "file": (io.BytesIO(data), name)},
                     content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200 and msg.lower() in r.get_data(as_text=True).lower()
    assert rows(app, "SELECT COUNT(*) c FROM players")[0]["c"] == 0


def test_too_many_rows_and_large_upload(app, admin):
    big = "Hold;Navn\n" + "\n".join(f"UB;Spiller {i}" for i in range(2100))
    r = admin.c.post("/admin/import", data={"csrf_token": admin.token("/admin/import"), "file": (io.BytesIO(big.encode()), "a.csv")},
                     content_type="multipart/form-data", follow_redirects=True)
    assert "mere end" in r.get_data(as_text=True)
    huge = admin.c.post("/admin/import", data={"csrf_token": "x", "file": (io.BytesIO(b"a" * (2 * 1024 * 1024)), "a.csv")},
                        content_type="multipart/form-data")
    assert huge.status_code == 413


def test_trainer_cannot_import_and_token_is_bound_to_admin(app, admin):
    make_team(admin, "A")
    t = make_trainer(app, admin, "tr", ["A"])
    for path in ("/admin/import", "/admin/import/template.csv", "/admin/import/commit"):
        assert t.c.get(path).status_code in (403, 405)
    assert t.c.post("/admin/import", data={"csrf_token": t.token("/")}).status_code == 403
    html = upload(admin, CSV.encode()).get_data(as_text=True)
    token = re.search(r'name="token" value="([^"]+)"', html).group(1)
    assert admin.post("/admin/import/commit", {"token": "../../etc/passwd", "confirm": "ja"}, page="/admin/import").status_code == 302
    assert admin.post("/admin/import/commit", {"token": token}, page="/admin/import").status_code == 302   # uden bekræftelse
    assert rows(app, "SELECT COUNT(*) c FROM players")[0]["c"] == 0


def test_audit_has_counts_not_names_and_stash_is_removed(app, admin):
    commit(admin, upload(admin, CSV.encode()).get_data(as_text=True))
    log = " ".join(f"{r['action']} {r['detail']}" for r in rows(app, "SELECT action, detail FROM audit_log"))
    assert "nye=3" in log and "Anna" not in log
    d = os.path.join(app.config["TEAMUDVIKLING_DATA_DIR"], "import")
    assert not [f for f in os.listdir(d) if f.endswith(".json")]


def test_templates_download_and_roundtrip(app, admin):
    c = admin.get("/admin/import/template.csv")
    assert c.status_code == 200 and b"Navn" in c.data
    x = admin.get("/admin/import/template.xlsx")
    assert x.status_code == 200 and x.data[:2] == b"PK"
    commit(admin, upload(admin, c.data).get_data(as_text=True))                  # skabelonen kan selv importeres
    assert rows(app, "SELECT name FROM players")[0]["name"] == "Anna Alfa"
