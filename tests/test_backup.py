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
