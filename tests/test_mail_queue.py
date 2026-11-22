"""E-mail-kø: genforsøg, opgivelse, indhold slettes, dobbeltsending og administrationsside."""
import time

from app import mail_queue, mailer
from app.db import connect
from test_clubs_invites import make_user, mailapp, sql, world  # noqa: F401


def _con(app):
    return connect(app.config["DATABASE"])


def _put(app, body="hemmeligt link"):
    con = _con(app)
    with app.test_request_context():
        mail_queue.enqueue(con, "a@example.dk", "Emne", body, "test")
    con.close()


def test_failure_retries_with_backoff_then_gives_up_and_wipes_body(world, monkeypatch):
    app = world[0]
    app.config["MAIL_BACKEND"] = "smtp"
    monkeypatch.setattr(mailer, "send", lambda *a: (_ for _ in ()).throw(OSError("nede")))
    _put(app)
    con = _con(app)
    with app.app_context():
        for attempt in range(1, mail_queue.MAX_ATTEMPTS + 1):
            sql(app, "UPDATE mail_queue SET next_try=0, locked_until=NULL")
            assert mail_queue.process(con) == 0
            row = con.execute("SELECT * FROM mail_queue").fetchone()
            assert row["attempts"] == attempt and row["last_error"] == "OSError"
            if attempt < mail_queue.MAX_ATTEMPTS:
                assert row["failed"] == 0 and row["body"] == "hemmeligt link" and row["next_try"] > time.time()
        assert row["failed"] == 1 and row["body"] == ""                          # opgivet: indholdet (engangslink) er væk
        assert mail_queue.process(con) == 0 and mail_queue.stats(con)["failed"] == 1
    con.close()


def test_success_sends_once_and_wipes_body(world):
    app = world[0]
    _put(app)
    con = _con(app)
    with app.app_context():
        mail_queue.process(con)
        assert mail_queue.process(con) == 0                                       # ikke sendt to gange
        row = con.execute("SELECT * FROM mail_queue").fetchone()
    con.close()
    assert row["sent_at"] and row["body"] == "" and row["last_error"] is None
    assert [m["to"] for m in app.extensions["outbox"] if m["subject"] == "Emne"] == ["a@example.dk"]


def test_locked_row_is_not_sent_by_second_worker(world):
    app = world[0]
    _put(app)
    sql(app, "UPDATE mail_queue SET next_try=0, locked_until=?", int(time.time()) + 100)
    con = _con(app)
    with app.app_context():
        assert mail_queue.process(con) == 0
    con.close()
    assert not [m for m in app.extensions.get("outbox", []) if m["subject"] == "Emne"]


def test_inbox_email_is_queued_and_admin_page_and_retry(world, monkeypatch):
    app, admin, ca, cb, ta, tb = world
    sql(app, "UPDATE users SET email='tina@example.dk' WHERE username='tina'")
    ca.post("/inbox/send", {"to": "club", "title": "Hej", "body": "Tekst", "email": "1"}, page="/inbox/")
    assert [m["to"] for m in app.extensions["outbox"] if m["subject"].endswith("Hej")] == ["tina@example.dk"]
    assert sql(app, "SELECT COUNT(*) n FROM mail_queue WHERE sent_at IS NOT NULL")[0]["n"] >= 1
    r = admin.get("/admin/mail")
    assert r.status_code == 200 and "tina@example.dk" in r.get_data(as_text=True) and "Tekst" not in r.get_data(as_text=True)
    assert ca.get("/admin/mail").status_code in (302, 403) and ta.get("/admin/mail").status_code in (302, 403)
    sql(app, "UPDATE mail_queue SET failed=1, sent_at=NULL, body='x' WHERE id=(SELECT MIN(id) FROM mail_queue)")
    assert admin.post("/admin/mail", {}, page="/admin/mail").status_code == 302
    assert sql(app, "SELECT failed FROM mail_queue ORDER BY id LIMIT 1")[0]["failed"] == 0
    assert ta.post("/admin/mail", {}, page="/").status_code in (302, 403)


def test_purge_removes_old_rows(world):
    app = world[0]
    _put(app)
    sql(app, "UPDATE mail_queue SET sent_at=?", int(time.time()) - 8 * 86400)
    con = _con(app)
    mail_queue.purge(con)
    assert con.execute("SELECT COUNT(*) FROM mail_queue").fetchone()[0] == 0
    con.close()
