"""E-mail-kø: mails lægges i tabellen mail_queue og sendes af en baggrundstråd med genforsøg, så brugeren ikke venter på SMTP.

Indholdet (brødtekst) slettes, så snart mailen er sendt eller opgivet (den kan indeholde engangslinks). Fejllog gemmer kun fejltypen.
"""
import threading
import time

from flask import current_app, g

from . import mailer

MAX_ATTEMPTS = 6
BACKOFF = (60, 300, 900, 3600, 10800)           # sekunder før genforsøg 2, 3, 4, 5, 6
LOCK_SECONDS = 120
KEEP_SENT_DAYS, KEEP_FAILED_DAYS = 7, 30


def enqueue(db, to, subject, body, kind="andet"):
    """Lægger en mail i køen og gemmer straks. Selve udsendelsen sker i baggrunden (i tests: efter forespørgslen)."""
    now = int(time.time())
    db.execute("INSERT INTO mail_queue(to_addr,subject,body,kind,created_at,next_try) VALUES(?,?,?,?,?,?)", (to, subject, body, kind, now, now))
    db.commit()
    g.mail_pending = True
    wake = current_app.extensions.get("mail_wake")
    if wake:
        wake.set()


def process(db, limit=25):
    """Sender forfaldne mails. Returnerer antal sendt. Hver række låses, så flere processer ikke sender det samme to gange."""
    now = int(time.time())
    rows = db.execute("SELECT id FROM mail_queue WHERE sent_at IS NULL AND failed=0 AND next_try<=? AND (locked_until IS NULL OR locked_until<?) ORDER BY id LIMIT ?",
                      (now, now, limit)).fetchall()
    sent = 0
    for r in rows:
        claim = db.execute("UPDATE mail_queue SET locked_until=? WHERE id=? AND sent_at IS NULL AND (locked_until IS NULL OR locked_until<?)", (now + LOCK_SECONDS, r["id"], now))
        db.commit()
        if claim.rowcount != 1:
            continue
        m = db.execute("SELECT * FROM mail_queue WHERE id=?", (r["id"],)).fetchone()
        try:
            mailer.send(m["to_addr"], m["subject"], m["body"])
        except Exception as exc:     # noqa: BLE001 – SMTP kan fejle på mange måder; kun typen logges
            attempts = m["attempts"] + 1
            if attempts >= MAX_ATTEMPTS:
                db.execute("UPDATE mail_queue SET attempts=?, failed=1, last_error=?, body='', locked_until=NULL WHERE id=?", (attempts, type(exc).__name__, m["id"]))
            else:
                db.execute("UPDATE mail_queue SET attempts=?, next_try=?, last_error=?, locked_until=NULL WHERE id=?",
                           (attempts, int(time.time()) + BACKOFF[min(attempts - 1, len(BACKOFF) - 1)], type(exc).__name__, m["id"]))
            current_app.logger.warning("Mail #%s kunne ikke sendes (%s), forsøg %s", m["id"], type(exc).__name__, attempts)
        else:
            db.execute("UPDATE mail_queue SET sent_at=?, attempts=attempts+1, body='', last_error=NULL, locked_until=NULL WHERE id=?", (int(time.time()), m["id"]))
            sent += 1
        db.commit()
    return sent


def purge(db):
    now = int(time.time())
    db.execute("DELETE FROM mail_queue WHERE (sent_at IS NOT NULL AND sent_at<?) OR (failed=1 AND created_at<?)", (now - KEEP_SENT_DAYS * 86400, now - KEEP_FAILED_DAYS * 86400))
    db.commit()


def stats(db):
    now = int(time.time())
    r = db.execute("SELECT SUM(sent_at IS NULL AND failed=0) pending, SUM(failed=1) failed, SUM(sent_at>?) sent24 FROM mail_queue", (now - 86400,)).fetchone()
    return dict(pending=r["pending"] or 0, failed=r["failed"] or 0, sent24=r["sent24"] or 0)


def retry_failed(db):
    n = db.execute("UPDATE mail_queue SET failed=0, attempts=0, next_try=?, last_error=NULL WHERE failed=1 AND body<>''", (int(time.time()),)).rowcount
    db.commit()
    return n


def after_request_drain(app):
    """Test-/hukommelsesbackend: send straks efter forespørgslen, så outbox kan tjekkes uden baggrundstråd."""
    if app.config.get("MAIL_BACKEND") == "memory" and g.get("mail_pending"):
        from .db import connect
        con = connect(app.config["DATABASE"])
        try:
            process(con)
        finally:
            con.close()


def start_worker(app):
    """Baggrundstråd (én pr. proces): sender mails (rækkelåsen forhindrer dobbeltsending mellem gunicorn-workers) og tager daglig backup."""
    if app.config.get("MAIL_BACKEND") == "memory" or app.config.get("TESTING") or app.config.get("MAIL_WORKER") == "0":
        return None
    wake = threading.Event()
    app.extensions["mail_wake"] = wake

    def loop():
        from .db import connect
        last_purge = 0
        while True:
            wake.wait(timeout=5)
            wake.clear()
            try:
                with app.app_context():
                    con = connect(app.config["DATABASE"])
                    try:
                        process(con)
                        if time.time() - last_purge > 3600:      # timevis vedligehold: oprydning + daglig backup (også uden login)
                            purge(con)
                            last_purge = time.time()
                            from .db import backup_if_due
                            backup_if_due(app.config["DATABASE"], app.config["BACKUP_DIR"])
                    finally:
                        con.close()
            except Exception:     # noqa: BLE001 – tråden må aldrig dø
                app.logger.exception("Mail-worker fejlede")
                time.sleep(10)
    t = threading.Thread(target=loop, name="mail-worker", daemon=True)
    t.start()
    return t
