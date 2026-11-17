import re
import time

from app import db, totp
from conftest import PW, Client


def test_fresh_database_has_no_player_data(app):
    con = db.connect(app.config["DATABASE"])
    for table in ("players", "evaluations", "motivation_answers", "devdata", "teams", "users"):
        assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    con.close()


def test_everything_requires_login(client):
    for path in ("/", "/players/", "/eval", "/overview", "/admin/", "/report/1", "/m"):
        r = client.get(path)
        assert r.status_code == 302 and "/login" in r.headers["Location"], path
    assert client.get("/healthz").status_code == 200
    assert client.get("/login").status_code in (200, 302)


def test_setup_creates_admin_and_forces_2fa(app):
    c = Client(app)
    r = c.post("/setup", {"username": "admin", "display_name": "A", "password": PW, "password2": PW}, page="/setup")
    assert r.status_code == 302 and "/2fa/setup" in r.headers["Location"]
    # før 2FA er fuldført, er resten af appen låst
    assert "/2fa/setup" in c.get("/players/").headers["Location"]
    page = c.get("/2fa/setup").get_data(as_text=True)
    secret = re.search(r'class="secret">([A-Z2-7]+)<', page).group(1)
    bad = c.post("/2fa/setup", {"code": "000000"}, page="/2fa/setup")
    assert "passer ikke" in bad.get_data(as_text=True)
    ok = c.post("/2fa/setup", {"code": totp.totp(secret)}, page="/2fa/setup")
    assert "Gendannelseskoder" in ok.get_data(as_text=True)
    assert c.get("/no-team").status_code == 200  # fuldt logget ind, men intet hold endnu
    # setup kan ikke bruges igen
    assert "/login" in Client(app).get("/setup").headers["Location"]


def test_weak_password_rejected(app):
    c = Client(app)
    r = c.post("/setup", {"username": "a", "password": "kort", "password2": "kort"}, page="/setup")
    assert r.status_code == 200 and "mindst 12" in r.get_data(as_text=True)


def test_setup_token_enforced(tmp_path, monkeypatch):
    monkeypatch.setenv("U11_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SETUP_TOKEN", "hemmelig")
    from app import create_app
    c = Client(create_app({"TESTING": True}))
    r = c.post("/setup", {"username": "a", "password": PW, "password2": PW, "setup_token": "forkert"}, page="/setup")
    assert "Forkert opsætningskode" in r.get_data(as_text=True)


def test_login_requires_second_factor_and_csrf(app, admin):
    c = Client(app)
    assert c.c.post("/login", data={"username": "admin", "password": PW}).status_code == 400     # ingen CSRF
    c.c.get("/login")
    r = c.post("/login", {"username": "admin", "password": PW}, page="/login")
    assert "/login/2fa" in r.headers["Location"]
    assert "/login/2fa" in c.get("/players/").headers["Location"]       # kun adgangskode er ikke nok
    time_step_next = totp.totp(admin.secret, time.time() + 30)            # næste tidstrin (det nuværende er brugt)
    r = c.post("/login/2fa", {"code": time_step_next}, page="/login/2fa")
    assert r.status_code == 302
    assert c.get("/no-team").status_code == 200


def test_totp_code_cannot_be_replayed(app, admin):
    c = Client(app)
    c.c.get("/login")
    c.post("/login", {"username": "admin", "password": PW}, page="/login")
    r = c.post("/login/2fa", {"code": totp.totp(admin.secret)}, page="/login/2fa")   # samme kode som ved opsætning
    assert r.status_code == 200 and "Forkert kode" in r.get_data(as_text=True)


def test_lockout_after_repeated_failures(app, admin):
    c = Client(app)
    for _ in range(5):
        c.c.get("/login")
        c.post("/login", {"username": "admin", "password": "forkert-forkert"}, page="/login")
    c.c.get("/login")
    r = c.post("/login", {"username": "admin", "password": PW}, page="/login")
    assert r.status_code == 200 and "låst" in r.get_data(as_text=True)      # korrekt kode afvises mens låst


def test_recovery_code_logs_in_once(app):
    c = Client(app)
    c.post("/setup", {"username": "admin", "password": PW, "password2": PW}, page="/setup")
    page = c.get("/2fa/setup").get_data(as_text=True)
    secret = re.search(r'class="secret">([A-Z2-7]+)<', page).group(1)
    html = c.post("/2fa/setup", {"code": totp.totp(secret)}, page="/2fa/setup").get_data(as_text=True)
    code = re.findall(r"<div>([0-9a-f]{4}-[0-9a-f]{4})</div>", html)[0]
    d = Client(app)
    d.c.get("/login")
    d.post("/login", {"username": "admin", "password": PW}, page="/login")
    assert d.post("/login/2fa", {"code": code}, page="/login/2fa").status_code == 302
    e = Client(app)
    e.c.get("/login")
    e.post("/login", {"username": "admin", "password": PW}, page="/login")
    assert e.post("/login/2fa", {"code": code}, page="/login/2fa").status_code == 200   # allerede brugt


def test_security_headers(client):
    r = client.get("/login")
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"
