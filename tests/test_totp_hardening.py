"""2FA-hærdning: hemmeligheder krypteres i hvile, og ny 2FA kræver adgangskoden igen."""
import sqlite3

from app import create_app, db as appdb, secrets_box
from conftest import PW, Client
from helpers import make_team, make_trainer


def raw(app, q, *a):
    con = sqlite3.connect(app.config["DATABASE"])
    con.row_factory = sqlite3.Row
    r = con.execute(q, a).fetchall()
    con.commit(); con.close()
    return r


def test_secret_is_encrypted_in_database_but_login_works(app, admin):
    stored = raw(app, "SELECT totp_secret FROM users WHERE username='admin'")[0]["totp_secret"]
    assert stored.startswith("enc1:") and admin.secret not in stored          # kun krypteret i databasen
    c = Client(app)
    assert c.login("admin", PW, secret=admin.secret).status_code in (200, 302)  # login med 2FA virker stadig


def test_plaintext_secrets_are_encrypted_on_startup(app, admin, tmp_path):
    raw(app, "UPDATE users SET totp_secret=? WHERE username='admin'", admin.secret)       # simulér ældre klartekst
    assert not raw(app, "SELECT totp_secret FROM users")[0]["totp_secret"].startswith("enc1:")
    app2 = create_app({"DATABASE": app.config["DATABASE"], "U11_DATA_DIR": app.config["U11_DATA_DIR"], "TESTING": True, "SECRET_KEY": "x" * 32})
    assert raw(app2, "SELECT totp_secret FROM users WHERE username='admin'")[0]["totp_secret"].startswith("enc1:")
    c = Client(app2)
    assert c.login("admin", PW, secret=admin.secret).status_code in (200, 302)


def test_wrong_key_rejects_2fa_instead_of_crashing(app, admin):
    key = secrets_box.load_key(app.config["U11_DATA_DIR"])
    other = secrets_box.Fernet.generate_key()
    token = secrets_box.encrypt(key, "ABCDEF")
    assert secrets_box.decrypt(other, token) is None and secrets_box.decrypt(key, token) == "ABCDEF"
    assert secrets_box.decrypt(key, "legacyplain") == "legacyplain"


def test_new_2fa_requires_password_reauth(app, admin):
    r = admin.get("/2fa/setup?ny=1")
    assert r.status_code == 302 and "/2fa/bekraeft" in r.headers["Location"]
    assert admin.post("/2fa/bekraeft", {"password": "forkert-adgangskode"}, page="/2fa/bekraeft").status_code == 200
    r = admin.post("/2fa/bekraeft", {"password": PW}, page="/2fa/bekraeft")
    assert r.status_code == 302 and "/2fa/setup" in r.headers["Location"]
    assert admin.get("/2fa/setup?ny=1").status_code == 200
