"""Runder (navn/dato/lukning), stoppede trænere og holdskifte."""
from datetime import date, timedelta

from app import db as appdb
from tests.test_clubs_invites import mailapp, world  # noqa: F401



def test_round_close_and_reopen(app, world):
    from app.helpers import ROUND_OPEN_DAYS
    assert ROUND_OPEN_DAYS == 30


def test_stop_user_keeps_evaluations(app, world):
    from app import transfer
    with app.app_context():
        db = appdb.get_db()
        uid = db.execute("SELECT id FROM users WHERE role='trainer' LIMIT 1").fetchone()[0]
        db.execute("INSERT INTO teams(name,created_at,club_id) VALUES('H','2026-01-01',NULL)")
        tid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute("INSERT INTO players(team_id,name,active) VALUES(?,?,1)", (tid, "Anna Alfa"))
        pid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute("INSERT INTO evaluations(round,player_id,trainer_id,crit,score) VALUES(1,?,?,0,4)", (pid, uid))
        assert transfer.has_evaluations(db, uid)
        transfer.stop_user(db, db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
        u = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        assert u["stopped_at"] and u["display_name"].endswith("(stoppet)") and u["pw_hash"] == "!stoppet"
        assert db.execute("SELECT COUNT(*) FROM evaluations WHERE trainer_id=?", (uid,)).fetchone()[0] == 1


def test_move_player_keeps_history(app, world):
    from app import transfer
    with app.app_context():
        db = appdb.get_db()
        uid = db.execute("SELECT id FROM users WHERE role='trainer' LIMIT 1").fetchone()[0]
        for n in ("A", "B"):
            db.execute("INSERT INTO teams(name,created_at) VALUES(?, '2026-01-01')", (n,))
        a, b = [r[0] for r in db.execute("SELECT id FROM teams WHERE name IN ('A','B') ORDER BY name")]
        db.execute("INSERT INTO players(team_id,name,active) VALUES(?,?,1)", (a, "Anna Alfa"))
        pid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        for c in range(24):
            db.execute("INSERT INTO evaluations(round,player_id,trainer_id,crit,score) VALUES(1,?,?,?,4)", (pid, uid, c))
        p = db.execute("SELECT * FROM players WHERE id=?", (pid,)).fetchone()
        transfer.move_player(db, p, db.execute("SELECT * FROM teams WHERE id=?", (b,)).fetchone(), "t")
        assert db.execute("SELECT team_id FROM players WHERE id=?", (pid,)).fetchone()[0] == b
        assert db.execute("SELECT COUNT(*) FROM evaluations WHERE player_id=?", (pid,)).fetchone()[0] == 0
        h = transfer.history(db, pid)
        assert h and h[0]["team"] == "A" and h[0]["rounds"][0]["samlet"] == 4


def test_profile_shows_only_complete_rounds(app, world):
    from app import model
    from app.evaluation import profile_data, complete_rounds
    from flask import g
    with app.test_request_context():
        db = appdb.get_db()
        uid = db.execute("SELECT id FROM users WHERE role='trainer' LIMIT 1").fetchone()[0]
        db.execute("INSERT INTO teams(name,created_at) VALUES('P','2026-01-01')")
        t = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        ids = []
        for n in ("Anna Alfa", "Bo Beta"):
            db.execute("INSERT INTO players(team_id,name,active) VALUES(?,?,1)", (t, n))
            ids.append(db.execute("SELECT last_insert_rowid()").fetchone()[0])
        for rnd, who in ((1, ids), (2, ids), (3, ids), (4, ids[:1])):       # runde 4 kun delvist
            for pid in who:
                for c in range(24):
                    db.execute("INSERT INTO evaluations(round,player_id,trainer_id,crit,score) VALUES(?,?,?,?,3)", (rnd, pid, uid, c))
        g.team = db.execute("SELECT * FROM teams WHERE id=?", (t,)).fetchone()
        g.rounds = (1, 2, 3, 4)
        rounds = model.load_rounds(db, t)
        assert complete_rounds(db, rounds) == [1, 2, 3]
        p = db.execute("SELECT * FROM players WHERE id=?", (ids[0],)).fetchone()
        d = profile_data(db, p, rounds)
        assert [i["no"] for i in d["infos"]] == [2, 3] and d["more"] == 1
        assert len(profile_data(db, p, rounds, show_all=True)["infos"]) == 3


def test_heat_colours():
    from app.charts import heat
    assert heat(1) == "#f8696b" and heat(2) == "#ffeb84" and heat(3) == "#63be7b"
    assert heat(4) == "#e0b020" and heat(5) == "#9dc3e6" and heat(None) == "#f2f2f2"
