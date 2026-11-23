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
