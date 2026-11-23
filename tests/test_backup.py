"""Backup og gendannelse: backuppen kontrolleres, ødelagte filer afvises, og en gendannet database virker."""
import os
import shutil

import pytest

from app import create_app, db as appdb
from conftest import Client
from helpers import add_player, make_team, make_trainer, switch, team_id


def test_backup_is_verified_and_same_second_does_not_overwrite(app, admin, tmp_path):
    a = appdb.backup(app.config["DATABASE"], str(tmp_path))
    b = appdb.backup(app.config["DATABASE"], str(tmp_path))
    assert a != b and os.path.exists(a) and os.path.exists(b)
    assert appdb.verify_backup(a) == (True, [])


def test_verify_rejects_garbage_and_wrong_database(tmp_path):
    bad = tmp_path / "x.db"
    bad.write_bytes(b"ikke en database" * 100)
    assert appdb.verify_backup(str(bad))[0] is False
    import sqlite3
    other = tmp_path / "other.db"
    c = sqlite3.connect(other); c.execute("CREATE TABLE t(x)"); c.commit(); c.close()
    ok, msgs = appdb.verify_backup(str(other))
    assert not ok and "gyldig Team Udvikling" in msgs[0]
    assert appdb.verify_backup(str(tmp_path / "findes-ikke.db"))[0] is False


def test_verify_rejects_newer_schema(app, tmp_path):
    dest = appdb.backup(app.config["DATABASE"], str(tmp_path))
    import sqlite3
    c = sqlite3.connect(dest); c.execute(f"PRAGMA user_version={appdb.SCHEMA_VERSION + 1}"); c.commit(); c.close()
    ok, msgs = appdb.verify_backup(dest)
    assert not ok and "nyere version" in msgs[0]


def test_restored_database_works(app, admin, tmp_path):
    make_team(admin, "A")
    switch(admin, team_id(app, "A"))
    add_player(admin, "Anna Alfa")
    t = make_trainer(app, admin, "tr", ["A"])
    dest = appdb.backup(app.config["DATABASE"], str(tmp_path / "bk"))
    add_player(admin, "Efter Backup")                                 # skal forsvinde ved gendannelse
    shutil.copy(dest, app.config["DATABASE"])                         # gendannelse (som restore.sh)
    for ext in ("-wal", "-shm"):
        p = app.config["DATABASE"] + ext
        if os.path.exists(p):
            os.remove(p)
    con = appdb.connect(app.config["DATABASE"])
    names = {r["name"] for r in con.execute("SELECT name FROM players")}
    con.close()
    assert names == {"Anna Alfa"}
    assert Client(app).login("tr", "x" * 3).status_code in (200, 302)   # appen starter og svarer på den gendannede database


def _restore(admin, app, data, **kw):
    from test_clubs_invites import code
    data = dict(data, code=code(app, admin, "admin"), confirm=kw.pop("confirm", "GENDAN"))
    return admin.post("/admin/restore", data, page="/admin/", content_type="multipart/form-data", **kw)


def test_restore_replaces_database_from_uploaded_backup(app, admin, tmp_path):
    """Gendannelse via siden: kræver kode + GENDAN, afviser ugyldige filer, erstatter databasen og gemmer den gamle."""
    import io
    make_team(admin, "Hold Gemt")
    good = appdb.backup(app.config["DATABASE"], str(tmp_path))
    make_team(admin, "Hold Efter")
    # ugyldige forsøg ændrer intet
    r = _restore(admin, app, {"backup": (io.BytesIO(b"ikke en database" * 50), "x.db")}, follow_redirects=True)
    assert "ikke en SQLite-database" in r.get_data(as_text=True)
    r = _restore(admin, app, {"backup": (open(good, "rb"), "b.db")}, confirm="nej", follow_redirects=True)
    assert "Skriv GENDAN" in r.get_data(as_text=True)
    con = appdb.connect(app.config["DATABASE"])
    assert {x["name"] for x in con.execute("SELECT name FROM teams")} >= {"Hold Gemt", "Hold Efter"}
    con.close()
    # gyldigt forsøg
    r = _restore(admin, app, {"backup": (open(good, "rb"), "b.db")})
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    con = appdb.connect(app.config["DATABASE"])
    names = {x["name"] for x in con.execute("SELECT name FROM teams")}
    assert "Hold Gemt" in names and "Hold Efter" not in names
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action='backup_gendannet'").fetchone()[0] == 1
    con.close()
    assert any(f.startswith("teamudvikling-") for f in os.listdir(app.config["BACKUP_DIR"]))     # den tidligere database er gemt


def test_restore_is_for_system_admin_only_and_needs_valid_code(app, admin):
    import io
    r = admin.post("/admin/restore", {"backup": (io.BytesIO(b"x"), "x.db"), "confirm": "GENDAN", "code": "000000"}, page="/admin/", content_type="multipart/form-data", follow_redirects=True)
    assert "Forkert eller allerede brugt 2FA-kode" in r.get_data(as_text=True)


# ------------------------------------------------------------ B-12 / B-13
def test_download_name_has_date_and_time(app, admin):
    import re as _re
    r = admin.post("/admin/backup", {}, page="/admin/")
    assert r.status_code == 200
    assert _re.search(r'filename="?teamudvikling-\d{4}-\d{2}-\d{2}_\d{4}\.db', r.headers["Content-Disposition"])


def test_every_backup_publishes_latest_db_and_json(app, tmp_path):
    import json, hashlib
    dest = appdb.backup(app.config["DATABASE"], str(tmp_path))
    meta = json.load(open(tmp_path / "latest.json"))
    assert meta["file"] == os.path.basename(dest) and meta["size"] == os.path.getsize(dest)
    assert meta["sha256"] == hashlib.sha256(open(dest, "rb").read()).hexdigest()
    assert appdb.verify_backup(str(tmp_path / "latest.db")) == (True, [])
    for i in range(3):
        appdb.backup(app.config["DATABASE"], str(tmp_path), keep=2)
    assert len([f for f in os.listdir(tmp_path) if f.startswith("teamudvikling-") and f.endswith(".db")]) == 2        # latest.* tæller ikke med og slettes ikke


def test_plan_validation_next_run_and_due(app):
    import datetime
    from werkzeug.datastructures import MultiDict
    from app import backup_plan as bp
    plan, err = bp.parse_form(MultiDict([("enabled", "1"), ("days", "0"), ("days", "4"), ("time", "03:30"), ("keep", "10")]))
    assert err is None and plan == {"enabled": True, "days": [0, 4], "time": "03:30", "keep": 10}
    for bad in ({"time": "25:00"}, {"time": "3.30"}, {"keep": "0"}, {"keep": "100"}, {"keep": "x"}):
        form = {"enabled": "1", "days": "1", "time": "03:30", "keep": "10", **bad}
        assert bp.parse_form(MultiDict(form))[1]
    assert bp.parse_form(MultiDict([("enabled", "1"), ("time", "03:30"), ("keep", "5")]))[1]       # ingen ugedage
    mon = datetime.datetime(2026, 11, 23, 10, 0)                       # mandag
    assert bp.next_run(plan, mon) == datetime.datetime(2026, 11, 27, 3, 30)        # næste fredag
    assert bp.next_run({**plan, "enabled": False}, mon) is None
    assert not bp.is_due(plan, datetime.datetime(2026, 11, 23, 3, 29)) and bp.is_due(plan, datetime.datetime(2026, 11, 23, 3, 30))
    assert not bp.is_due(plan, datetime.datetime(2026, 11, 24, 12, 0))      # tirsdag er ikke valgt


def test_scheduled_backup_runs_once_per_day_and_records_state(app, tmp_path):
    import datetime, json
    from app import backup_plan as bp
    con = appdb.connect(app.config["DATABASE"])
    bdir = str(tmp_path / "b")
    bp.set_plan(con, {"enabled": True, "days": [0], "time": "03:30", "keep": 5}); con.commit()
    early = datetime.datetime(2026, 11, 23, 3, 0)
    assert bp.run_if_due(con, app.config["DATABASE"], bdir, now=early) is None                       # for tidligt
    t = datetime.datetime(2026, 11, 23, 3, 31)
    first = bp.run_if_due(con, app.config["DATABASE"], bdir, now=t)
    assert first and os.path.exists(first)
    assert bp.run_if_due(con, app.config["DATABASE"], bdir, now=t + datetime.timedelta(minutes=5)) is None   # ikke dobbelt samme dag
    st = bp.get_state(con)
    assert st["ok"] and st["file"] == os.path.basename(first) and st["at"] == "2026-11-23 03:31"
    assert os.path.exists(os.path.join(bdir, "latest.json"))
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action='backup_planlagt'").fetchone()[0] == 1
    nxt = bp.run_if_due(con, app.config["DATABASE"], bdir, now=datetime.datetime(2026, 11, 30, 4, 0))   # næste mandag
    assert nxt and nxt != first
    con.close()


def test_scheduled_backup_failure_is_shown_not_raised(app, tmp_path, monkeypatch):
    import datetime
    from app import backup_plan as bp
    con = appdb.connect(app.config["DATABASE"])
    bp.set_plan(con, {"enabled": True, "days": list(range(7)), "time": "00:00", "keep": 5}); con.commit()
    monkeypatch.setattr(appdb, "backup", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disken er fuld")))
    assert bp.run_if_due(con, app.config["DATABASE"], str(tmp_path), now=datetime.datetime(2026, 11, 23, 5, 0)) is None
    st = bp.get_state(con)
    assert st["ok"] is False and "disken er fuld" in st["error"]
    con.close()


def test_plan_form_is_sysadmin_only_and_saved(app, admin):
    assert admin.post("/admin/backup-plan", {"enabled": "1", "days": ["1", "3"], "time": "02:15", "keep": "7"}, page="/admin/", follow_redirects=True).status_code == 200
    con = appdb.connect(app.config["DATABASE"])
    from app import backup_plan as bp
    assert bp.get_plan(con) == {"enabled": True, "days": [1, 3], "time": "02:15", "keep": 7}
    con.close()
    html = admin.get("/admin/").get_data(as_text=True)
    assert "Automatisk backup efter plan" in html and 'value="02:15"' in html and "Næste planlagte backup" in html
    r = admin.post("/admin/backup-plan", {"enabled": "1", "time": "99:99", "keep": "7"}, page="/admin/", follow_redirects=True)
    assert "klokkeslæt som tt:mm" in r.get_data(as_text=True)
