"""B-040: migrationsrunner – én gang, log, rollback, backup før ændring, samme skema for ny og gammel database."""
import os
import sqlite3

import pytest

from app import db as appdb


def dump(path):
    con = sqlite3.connect(path)
    rows = sorted((r[0], r[1], r[2]) for r in con.execute("SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND name<>'schema_migrations'"))
    con.close()
    return rows


def test_fresh_and_repeated_init_give_same_schema_and_log(tmp_path):
    p = str(tmp_path / "a.db")
    appdb.init_db(p)
    first = dump(p)
    appdb.init_db(p)
    assert dump(p) == first
    con = sqlite3.connect(p)
    ids = [r[0] for r in con.execute("SELECT id FROM schema_migrations ORDER BY id")]
    con.close()
    assert ids == [m[0] for m in appdb.MIGRATIONS]


def test_old_database_without_log_is_brought_up_to_same_schema(tmp_path):
    fresh, old = str(tmp_path / "f.db"), str(tmp_path / "o.db")
    appdb.init_db(fresh)
    appdb.init_db(old)
    con = sqlite3.connect(old)
    con.execute("DROP TABLE schema_migrations")            # som en database fra før migrationsrunneren
    con.execute("PRAGMA user_version=21")
    con.commit(); con.close()
    appdb.init_db(old, backup_dir=str(tmp_path / "bk"))
    assert dump(old) == dump(fresh)
    assert any(f.startswith("pre-migration-") for f in os.listdir(tmp_path / "bk"))        # backup før ændring


def test_new_migration_runs_once_and_failure_rolls_back(tmp_path):
    p = str(tmp_path / "m.db")
    appdb.init_db(p)
    calls = []

    def add_col(con):
        calls.append(1)
        con.execute("ALTER TABLE clubs ADD COLUMN testcol TEXT")

    def bad(con):
        con.execute("ALTER TABLE clubs ADD COLUMN halfdone TEXT")
        raise ValueError("boom")

    ms = appdb.MIGRATIONS + [("900_test", add_col)]
    appdb.init_db(p, migrations=ms)
    appdb.init_db(p, migrations=ms)
    assert calls == [1]                                      # kun én gang
    with pytest.raises(appdb.MigrationError):
        appdb.init_db(p, migrations=ms + [("901_bad", bad)])
    con = sqlite3.connect(p)
    cols = {r[1] for r in con.execute("PRAGMA table_info(clubs)")}
    done = {r[0] for r in con.execute("SELECT id FROM schema_migrations")}
    con.close()
    assert "testcol" in cols and "halfdone" not in cols and "901_bad" not in done        # rullet tilbage, ikke logget


def test_no_backup_for_empty_new_database(tmp_path):
    appdb.init_db(str(tmp_path / "n.db"), backup_dir=str(tmp_path / "bk"))
    assert not (tmp_path / "bk").exists()


def test_013_moves_criteria_texts_from_settings_to_table(tmp_path):
    p = str(tmp_path / "c.db")
    appdb.init_db(p)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    cid = con.execute("SELECT id FROM clubs LIMIT 1").fetchone()
    con.execute("INSERT INTO teams(name, club_id, created_at) VALUES('Hold A', ?, '2026-01-01')", (cid["id"] if cid else 1,))
    tid = con.execute("SELECT id FROM teams WHERE name='Hold A'").fetchone()["id"]
    con.execute("INSERT INTO settings(key,value) VALUES(?,?)", (f"t{tid}:crit_desc_3", "Egen tekst"))
    con.execute("INSERT INTO settings(key,value) VALUES(?,?)", (f"t{tid}:crit_desc_4", ""))
    con.execute("INSERT INTO settings(key,value) VALUES(?,?)", ("t9999:crit_desc_1", "Forældreløs"))
    con.execute("DELETE FROM schema_migrations WHERE id='013_team_kriterier'")
    con.execute("DROP TABLE team_criteria")
    con.commit()
    appdb._m013_team_criteria(con); con.commit()
    assert [(r["team_id"], r["idx"], r["description"]) for r in con.execute("SELECT * FROM team_criteria")] == [(tid, 3, "Egen tekst")]
    assert con.execute("SELECT COUNT(*) FROM settings WHERE key LIKE '%crit_desc%'").fetchone()[0] == 0
    appdb._m013_team_criteria(con); con.commit()                                              # idempotent
    assert con.execute("SELECT COUNT(*) FROM team_criteria").fetchone()[0] == 1
    con.close()
