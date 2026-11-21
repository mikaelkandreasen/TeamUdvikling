"""'Husk denne enhed i 30 dage' – sikkerhedsegenskaber."""
import time

import pytest

from app import create_app, totp
from conftest import PW, Client
from helpers import make_team, make_trainer
from test_import import rows

_step = [100]


def login(app, username, secret, remember=True, pw=PW, client=None):
    c = client or Client(app)
    c.c.get("/login")
    c.post("/login", {"username": username, "password": pw}, page="/login")
    from app import db
    con = db.connect(app.config["DATABASE"])
    con.execute("UPDATE users SET last_totp_step=0 WHERE username=?", (username,)); con.commit(); con.close()
    data = {"code": totp.totp(secret)}
    if remember:
        data["remember"] = "1"
    r = c.post("/login/2fa", data, page="/login/2fa")
    return c, r


def with_cookie(app, value, name="u11_rm"):
    cl = app.test_client()
    cl.set_cookie(name, value)
    return cl


def tok(c, name="u11_rm"):
    ck = c.c.get_cookie(name)
    return ck.value if ck else None


@pytest.fixture
def trainer(app, admin):
    make_team(admin, "A")
    t = make_trainer(app, admin, "tr", ["A"])
    return t


def test_remember_logs_in_without_password_or_2fa(app, trainer):
    c, r = login(app, "tr", trainer.secret)
    token = tok(c)
    assert token and len(token) >= 40
    fresh = with_cookie(app, token)
    assert fresh.get("/players/").status_code == 200
    h = rows(app, "SELECT token_hash FROM remember_tokens")[0]["token_hash"]
    assert token not in h and len(h) == 64                                   # kun nøglet hash gemmes


def test_not_remembered_when_box_unchecked(app, trainer):
    c, _ = login(app, "tr", trainer.secret, remember=False)
    assert tok(c) is None and rows(app, "SELECT COUNT(*) c FROM remember_tokens")[0]["c"] == 0


def test_cookie_flags_and_secure_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("U11_DATA_DIR", str(tmp_path)); monkeypatch.setenv("SETUP_TOKEN", "x"); monkeypatch.setenv("COOKIE_SECURE", "1")
    app = create_app({"TESTING": True})
    with app.test_request_context("/"):
        from app import remember
        assert remember.cookie_name() == "__Host-u11_rm"


def test_set_cookie_attributes(app, trainer):
    c = Client(app)
    c.c.get("/login")
    c.post("/login", {"username": "tr", "password": PW}, page="/login")
    from app import db
    con = db.connect(app.config["DATABASE"])
    con.execute("UPDATE users SET last_totp_step=0"); con.commit(); con.close()
    r = c.c.post("/login/2fa", data={"code": totp.totp(trainer.secret), "remember": "1", "csrf_token": c.token("/login/2fa")})
    header = [h for h in r.headers.getlist("Set-Cookie") if h.startswith("u11_rm=")][0]
    assert "HttpOnly" in header and "SameSite=Lax" in header and "Max-Age=" in header
    assert 29 * 86400 < int(header.split("Max-Age=")[1].split(";")[0]) <= 30 * 86400


def test_token_rotates_and_expiry_is_fixed(app, trainer):
    c, _ = login(app, "tr", trainer.secret)
    t1 = tok(c)
    exp1 = rows(app, "SELECT expires_at FROM remember_tokens")[0]["expires_at"]
    c2 = with_cookie(app, t1)
    c2.get("/players/")
    t2 = tok(type("X", (), {"c": c2})())
    assert t2 and t2 != t1
    assert rows(app, "SELECT expires_at FROM remember_tokens")[0]["expires_at"] == exp1       # fast 30 dage, ikke glidende


def test_reuse_of_old_token_after_grace_revokes_everything(app, trainer):
    c, _ = login(app, "tr", trainer.secret)
    old = tok(c)
    with_cookie(app, old).get("/players/")                                   # legitim brug → roterer
    from app import db
    con = db.connect(app.config["DATABASE"])
    con.execute("UPDATE remember_tokens SET rotated_at=rotated_at-3600"); con.commit(); con.close()
    thief = with_cookie(app, old)                                            # angriber bruger kopi af det gamle token
    assert thief.get("/players/").status_code == 302
    assert rows(app, "SELECT COUNT(*) c FROM remember_tokens")[0]["c"] == 0  # alle enheder tilbagekaldt
    assert "husk_enhed_misbrug" in " ".join(r["action"] for r in rows(app, "SELECT action FROM audit_log"))


def test_parallel_request_with_old_token_inside_grace_is_ok(app, trainer):
    c, _ = login(app, "tr", trainer.secret)
    old = tok(c)
    with_cookie(app, old).get("/players/")
    assert with_cookie(app, old).get("/players/").status_code == 200
    assert rows(app, "SELECT COUNT(*) c FROM remember_tokens")[0]["c"] == 1


def test_expired_token_requires_login(app, trainer):
    c, _ = login(app, "tr", trainer.secret)
    from app import db
    con = db.connect(app.config["DATABASE"])
    con.execute("UPDATE remember_tokens SET expires_at=?", (int(time.time()) - 1,)); con.commit(); con.close()
    assert with_cookie(app, tok(c)).get("/players/").status_code == 302


def test_logout_revokes_this_device(app, trainer):
    c, _ = login(app, "tr", trainer.secret)
    token = tok(c)
    c.post("/logout", {}, page="/")
    assert with_cookie(app, token).get("/players/").status_code == 302


def test_password_change_and_admin_resets_revoke(app, admin, trainer):
    c, _ = login(app, "tr", trainer.secret)
    token = tok(c)
    assert with_cookie(app, token).get("/players/").status_code == 200
    uid = rows(app, "SELECT id FROM users WHERE username='tr'")[0]["id"]
    admin.post(f"/admin/users/{uid}/reset-2fa", {"code": _fresh_code(app, admin)}, page="/admin/users")
    assert rows(app, "SELECT COUNT(*) c FROM remember_tokens")[0]["c"] == 0


def test_password_change_revokes_remembered_devices(app, admin, trainer):
    c, _ = login(app, "tr", trainer.secret)
    token = tok(c)
    c.post("/account", {"action": "password", "old": PW, "new": PW + "ny1", "new2": PW + "ny1"}, page="/account")
    assert with_cookie(app, token).get("/players/").status_code == 302


def test_forget_all_devices_button(app, trainer):
    c, _ = login(app, "tr", trainer.secret)
    token = tok(c)
    assert "1 enhed" in c.get("/account").get_data(as_text=True)
    c.post("/account", {"action": "forget_devices"}, page="/account")
    assert with_cookie(app, token).get("/players/").status_code == 302


def test_admin_requires_fresh_login_on_remembered_device(app, admin):
    c, _ = login(app, "admin", admin.secret)
    assert c.get("/admin/").status_code == 200                               # frisk login: ok
    token = tok(c)
    d = with_cookie(app, token)
    assert d.get("/players/").status_code in (200, 302)                      # almindelige sider: husket
    r = d.get("/admin/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]       # administration: trin-op
    assert rows(app, "SELECT COUNT(*) c FROM remember_tokens")[0]["c"] == 0  # enheden er ikke længere husket
    r2 = with_cookie(app, token).get("/admin/")
    assert r2.status_code == 302 and "/login" in r2.headers["Location"]


def test_locked_user_cannot_restore_and_tokens_limit(app, admin, trainer):
    c, _ = login(app, "tr", trainer.secret)
    token = tok(c)
    from app import db
    con = db.connect(app.config["DATABASE"])
    con.execute("UPDATE users SET locked_until=?", (int(time.time()) + 600,)); con.commit(); con.close()
    assert with_cookie(app, token).get("/players/").status_code == 302
    con = db.connect(app.config["DATABASE"])
    con.execute("UPDATE users SET locked_until=0"); con.commit(); con.close()
    for _ in range(12):
        login(app, "tr", trainer.secret)
    assert rows(app, "SELECT COUNT(*) c FROM remember_tokens")[0]["c"] == 10


def test_feature_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("U11_DATA_DIR", str(tmp_path)); monkeypatch.setenv("SETUP_TOKEN", "x"); monkeypatch.setenv("REMEMBER_DAYS", "0")
    app = create_app({"TESTING": True})
    with app.test_request_context("/"):
        from app import remember
        assert remember.days() == 0


def test_garbage_cookie_is_harmless(app, trainer):
    for v in ("x", "A" * 43, "../../etc", "%00"):
        r = with_cookie(app, v).get("/players/")
        assert r.status_code == 302 and "/login" in r.headers["Location"]


def _fresh_code(app, admin):
    from app import db as _db, totp as _totp
    con = _db.connect(app.config["DATABASE"]); con.execute("UPDATE users SET last_totp_step=0 WHERE username='admin'"); con.commit(); con.close()
    return _totp.totp(admin.secret)
