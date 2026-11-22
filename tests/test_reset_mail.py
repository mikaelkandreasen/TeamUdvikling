"""E-mail på brugere og nulstilling af adgangskode/2FA via mail efter administrators 2FA-godkendelse."""
import re
import sqlite3
import time

import pytest

from app import db as appdb, totp
from conftest import PW, Client
from helpers import make_team, make_trainer

BASE = "https://t.example"


@pytest.fixture
def mailapp(app):
    app.config.update(MAIL_BACKEND="memory", PUBLIC_URL=BASE, SMTP_FROM="u11@t.example")
    return app


@pytest.fixture
def setup(mailapp, admin):
    make_team(admin, "U11 Alfa")
    tr = make_trainer(mailapp, admin, "anna", ["U11 Alfa"], email="Anna@Example.DK")
    return mailapp, admin, tr


def uid(app, name):
    con = appdb.connect(app.config["DATABASE"])
    r = con.execute("SELECT id FROM users WHERE username=?", (name,)).fetchone()["id"]
    con.close()
    return r


def sql(app, q, *a):
    con = appdb.connect(app.config["DATABASE"])
    rows = con.execute(q, a).fetchall()
    con.commit()
    con.close()
    return rows


def code(app, admin):
    """Frisk, ubrugt 2FA-kode til administrator (nulstiller replay-tælleren som i de øvrige tests)."""
    sql(app, "UPDATE users SET last_totp_step=0 WHERE username='admin'")
    return totp.totp(admin.secret)


def login_as(app, name, pw, secret):
    """Login med nulstillet replay-tæller og ulåst konto (kodens tidstrin er ellers brugt af trænerens første login)."""
    sql(app, "UPDATE users SET last_totp_step=0, failed_logins=0, locked_until=0 WHERE username=?", name)
    c = Client(app)
    return c, c.login(name, pw, secret=secret)


def request_mail(app, admin, user, purpose="password", c=None):
    c = c if c is not None else code(app, admin)
    return admin.post(f"/admin/users/{uid(app, user)}/mail-reset", {"purpose": purpose, "code": c},
                      page="/admin/users", follow_redirects=True)


def outbox(app):
    return app.extensions.get("outbox", [])


def link_of(app):
    m = re.search(r"https://t\.example(/nulstil/[\w-]+)", outbox(app)[-1]["body"])
    return m.group(1)


def test_email_validation_and_storage(setup):
    app, admin, _ = setup
    assert sql(app, "SELECT email FROM users WHERE username='anna'")[0]["email"] == "anna@example.dk"      # normaliseret
    for bad in ("ikke-en-mail", "a@b", "a b@c.dk", "x@y.dk\nBcc: evil@z.dk"):
        r = admin.post(f"/admin/users/{uid(app, 'anna')}/email", {"email": bad}, page="/admin/users", follow_redirects=True)
        assert "Ugyldig e-mailadresse" in r.get_data(as_text=True)
    assert sql(app, "SELECT email FROM users WHERE username='anna'")[0]["email"] == "anna@example.dk"
    admin.post(f"/admin/users/{uid(app, 'anna')}/email", {"email": ""}, page="/admin/users")
    assert sql(app, "SELECT email FROM users WHERE username='anna'")[0]["email"] is None


def test_create_user_rejects_bad_email(mailapp, admin):
    r = admin.post("/admin/users", {"username": "bo", "role": "trainer", "email": "nope"}, page="/admin/users")
    assert "Ugyldig e-mailadresse" in r.get_data(as_text=True)
    assert not sql(mailapp, "SELECT 1 FROM users WHERE username='bo'")


def test_trainer_sees_email_read_only_and_cannot_use_admin(setup):
    app, admin, tr = setup
    assert "anna@example.dk" in tr.get("/account").get_data(as_text=True)
    r = tr.post(f"/admin/users/{uid(app, 'anna')}/mail-reset", {"purpose": "password", "code": "123456"}, page="/account")
    assert r.status_code == 403
    r = tr.post(f"/admin/users/{uid(app, 'anna')}/email", {"email": "evil@x.dk"}, page="/account")
    assert r.status_code == 403
    assert sql(app, "SELECT email FROM users WHERE username='anna'")[0]["email"] == "anna@example.dk"


def test_mail_requires_admin_2fa_code(setup):
    app, admin, _ = setup
    r = request_mail(app, admin, "anna", c="000000")
    assert "Forkert eller allerede brugt" in r.get_data(as_text=True)
    assert outbox(app) == [] and not sql(app, "SELECT 1 FROM reset_tokens")
    c = code(app, admin)
    r = request_mail(app, admin, "anna", c=c)
    assert "E-mail sendt" in r.get_data(as_text=True) and len(outbox(app)) == 1
    r = request_mail(app, admin, "anna", c=c)                       # samme kode igen = replay
    assert "Forkert eller allerede brugt" in r.get_data(as_text=True) and len(outbox(app)) == 1


def test_wrong_codes_lock_the_admin_out(setup):
    app, admin, _ = setup
    for _ in range(12):
        r = request_mail(app, admin, "anna", c="000000")
        if "/login" in r.request.path:
            break
    assert r.request.path == "/login" or sql(app, "SELECT locked_until FROM users WHERE username='admin'")[0][0] > time.time()
    assert outbox(app) == []


def test_mail_contents_and_token_storage(setup):
    app, admin, _ = setup
    request_mail(app, admin, "anna")
    mail = outbox(app)[0]
    assert mail["to"] == "anna@example.dk"
    token = link_of(app).rsplit("/", 1)[1]
    assert PW not in mail["body"] and "adgangskode" in mail["body"]
    stored = sql(app, "SELECT token_hash FROM reset_tokens")[0]["token_hash"]
    assert token not in stored and len(stored) == 64               # kun hash i databasen
    log = " ".join(f"{r['action']} {r['detail']}" for r in sql(app, "SELECT action, detail FROM audit_log"))
    assert "mail_nulstil_sendt" in log and token not in log and "example.dk" not in log


def test_password_reset_via_link(setup):
    app, admin, tr = setup
    request_mail(app, admin, "anna")
    path = link_of(app)
    pub = Client(app)
    assert pub.get(path).status_code == 200 and pub.get(path).status_code == 200      # GET forbruger ikke tokenet
    weak = pub.post(path, {"new": "kort", "new2": "kort"}, page=path)
    assert "mindst 12 tegn" in weak.get_data(as_text=True)
    new = "helt-ny-adgangskode-77"
    r = pub.post(path, {"new": new, "new2": new}, page=path)
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    # gammel adgangskode virker ikke, ny kræver stadig 2FA
    assert login_as(app, "anna", PW, tr.secret)[1].status_code == 200
    c, r = login_as(app, "anna", new, tr.secret)
    assert r.status_code == 302 and c.get("/").status_code == 200
    # engangs
    assert pub.post(path, {"new": new, "new2": new}, page=path).status_code == 400
    assert Client(app).get(path).status_code == 400


def test_password_reset_needs_2fa_afterwards(setup):
    app, admin, tr = setup
    request_mail(app, admin, "anna")
    path = link_of(app)
    new = "helt-ny-adgangskode-77"
    Client(app).post(path, {"new": new, "new2": new}, page=path)
    c = Client(app)
    c.c.get("/login")
    r = c.post("/login", {"username": "anna", "password": new}, page="/login")
    assert r.headers["Location"].endswith("/login/2fa")           # ingen adgang uden kode
    assert c.get("/").status_code == 302


def test_totp_reset_requires_password_and_replaces_secret(setup):
    app, admin, tr = setup
    old_secret = tr.secret
    request_mail(app, admin, "anna", "totp")
    path = link_of(app)
    pub = Client(app)
    r = pub.post(path, {"password": "forkert-forkert-12"}, page=path)
    assert "Forkert adgangskode" in r.get_data(as_text=True)
    assert sql(app, "SELECT totp_enabled FROM users WHERE username='anna'")[0][0] == 1    # intet nulstillet endnu
    r = pub.post(path, {"password": PW}, page=path)
    assert r.status_code == 302 and "/2fa/setup" in r.headers["Location"]
    assert sql(app, "SELECT totp_enabled FROM users WHERE username='anna'")[0][0] == 0
    page = pub.get("/2fa/setup").get_data(as_text=True)
    new_secret = re.search(r'class="secret">([A-Z2-7]+)<', page).group(1)
    assert new_secret != old_secret
    r = pub.post("/2fa/setup", {"code": totp.totp(new_secret)}, page="/2fa/setup")
    assert "gendannelseskoder" in r.get_data(as_text=True).lower()
    assert login_as(app, "anna", PW, old_secret)[1].status_code == 200            # gammel app-nøgle er død
    assert login_as(app, "anna", PW, new_secret)[1].status_code == 302
    assert Client(app).post(path, {"password": PW}, page=path).status_code == 400   # engangs


def test_email_alone_cannot_bypass_2fa(setup):
    app, admin, _ = setup
    request_mail(app, admin, "anna", "totp")
    path = link_of(app)
    pub = Client(app)
    assert pub.get(path).status_code == 200
    assert pub.get("/").status_code == 302                       # kun linket giver intet login
    assert sql(app, "SELECT totp_enabled FROM users WHERE username='anna'")[0][0] == 1


def test_expired_and_resent_links(setup):
    app, admin, _ = setup
    request_mail(app, admin, "anna")
    first = link_of(app)
    request_mail(app, admin, "anna")
    second = link_of(app)
    assert first != second
    assert Client(app).get(first).status_code == 400            # nyt link ugyldiggør det gamle
    sql(app, "UPDATE reset_tokens SET expires_at=? WHERE used_at IS NULL", int(time.time()) - 1)
    assert Client(app).get(second).status_code == 400


def test_rate_limit_per_user(setup):
    app, admin, _ = setup
    for _ in range(3):
        assert "E-mail sendt" in request_mail(app, admin, "anna").get_data(as_text=True)
    r = request_mail(app, admin, "anna")
    assert "for mange nulstillinger" in r.get_data(as_text=True) and len(outbox(app)) == 3


def test_changing_email_or_password_kills_pending_links(setup):
    app, admin, tr = setup
    request_mail(app, admin, "anna")
    path = link_of(app)
    admin.post(f"/admin/users/{uid(app, 'anna')}/email", {"email": "ny@example.dk"}, page="/admin/users")
    assert Client(app).get(path).status_code == 400
    request_mail(app, admin, "anna")
    path = link_of(app)
    tr.post("/account", {"action": "password", "old": PW, "new": "endnu-en-ny-kode-99", "new2": "endnu-en-ny-kode-99"}, page="/account")
    assert Client(app).get(path).status_code == 400


def test_not_configured_or_no_email(app, admin):
    make_team(admin, "U11 Alfa")
    make_trainer(app, admin, "bo", ["U11 Alfa"])                     # ingen e-mail, og mail er ikke sat op
    r = admin.get("/admin/users")
    assert "Send nulstilling på e-mail" not in r.get_data(as_text=True)
    app.config.update(MAIL_BACKEND="memory", PUBLIC_URL=BASE)
    r = request_mail(app, admin, "bo")
    assert "ingen e-mailadresse" in r.get_data(as_text=True) and outbox(app) == []
    app.config.update(PUBLIC_URL="")
    admin.post(f"/admin/users/{uid(app, 'bo')}/email", {"email": "bo@example.dk"}, page="/admin/users")
    r = request_mail(app, admin, "bo")
    assert "PUBLIC_URL" in r.get_data(as_text=True) and outbox(app) == []


def test_smtp_failure_leaves_no_token(setup, monkeypatch):
    app, admin, _ = setup
    from app import mailer

    def boom(*a, **k):
        raise OSError("nede")
    monkeypatch.setattr(mailer, "send", boom)
    r = request_mail(app, admin, "anna")
    assert "kunne ikke sendes" in r.get_data(as_text=True)
    assert not sql(app, "SELECT 1 FROM reset_tokens WHERE used_at IS NULL")


def test_bad_token_is_public_400_and_throttled(app):
    c = Client(app)
    assert c.get("/nulstil/ikke-et-token").status_code == 400            # ikke omdirigeret til login
    codes = {c.get("/nulstil/ikke-et-token").status_code for _ in range(25)}
    assert 429 in codes


def test_view_as_cannot_send_mail(setup):
    app, admin, _ = setup
    admin.post(f"/admin/users/{uid(app, 'anna')}/view-as", {}, page="/admin/users")
    r = admin.post(f"/admin/users/{uid(app, 'anna')}/mail-reset", {"purpose": "password", "code": code(app, admin)}, page="/")
    assert r.status_code == 403 and outbox(app) == []


def test_migration_adds_email_column_without_data_loss(tmp_path):
    path = str(tmp_path / "old.db")
    con = sqlite3.connect(path)
    con.executescript("""CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, display_name TEXT NOT NULL,
      pw_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'trainer', totp_secret TEXT, totp_enabled INTEGER NOT NULL DEFAULT 0,
      last_totp_step INTEGER NOT NULL DEFAULT 0, failed_logins INTEGER NOT NULL DEFAULT 0, locked_until INTEGER NOT NULL DEFAULT 0,
      must_change_pw INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
      INSERT INTO users(username,display_name,pw_hash,created_at) VALUES('gammel','Gammel','x','2026-01-01');""")
    con.commit()
    con.close()
    appdb.init_db(path)
    appdb.init_db(path)                                          # idempotent
    con = appdb.connect(path)
    row = con.execute("SELECT username, email FROM users").fetchone()
    assert row["username"] == "gammel" and row["email"] is None
    assert con.execute("SELECT COUNT(*) FROM reset_tokens").fetchone()[0] == 0
    assert con.execute("PRAGMA user_version").fetchone()[0] == appdb.SCHEMA_VERSION == 24
    con.close()


def test_smtp_send_uses_starttls_and_login(app, monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["conn"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context=None):
            sent["tls"] = True

        def login(self, u, p):
            sent["login"] = (u, p)

        def send_message(self, msg):
            sent["msg"] = msg

    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    app.config.update(SMTP_HOST="smtp.t.example", SMTP_PORT="2525", SMTP_USER="u", SMTP_PASSWORD="p", SMTP_FROM="u11@t.example")
    from app import mailer
    with app.app_context():
        mailer.send("a@b.dk", "Emne", "Tekst")
        with pytest.raises(ValueError):
            mailer.send("a@b.dk", "Emne\nBcc: x@y.dk", "Tekst")        # header-injektion afvises
    assert sent["conn"] == ("smtp.t.example", 2525) and sent["tls"] and sent["login"] == ("u", "p")
    assert sent["msg"]["To"] == "a@b.dk"
