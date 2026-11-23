"""Simuleret angreb på login bag Cloudflare (Tunnel/proxy). Hver test er et angreb; testen består, når angrebet fejler.

Cloudflare simuleres som en proxy foran appen: den SÆTTER X-Forwarded-Proto: https og TILFØJER klientens rigtige IP sidst i
X-Forwarded-For (en angriber kan selv sætte en falsk værdi først), samt CF-Connecting-IP. Appen kører som i drift
(TRUSTED_PROXIES=1, sikre cookies med __Host-præfiks). Se docs/SECURITY.md.
"""
import re
import statistics
import time

import pytest

from app import create_app, db as appdb, totp
from conftest import PW, Client
from helpers import make_team, make_trainer


class Edge:
    def __init__(self, app, ip="203.0.113.10"):
        self.ip, self.spoof = ip, None
        inner = app.wsgi_app

        def cloudflare(environ, start):
            attacker = self.spoof or environ.get("HTTP_X_FORWARDED_FOR")
            environ["HTTP_X_FORWARDED_FOR"] = ", ".join(x for x in (attacker, self.ip) if x)
            environ["HTTP_X_FORWARDED_PROTO"] = "https"
            environ["HTTP_CF_CONNECTING_IP"] = self.ip
            return inner(environ, start)
        app.wsgi_app = cloudflare


@pytest.fixture
def prod(tmp_path, monkeypatch):
    monkeypatch.setenv("TEAMUDVIKLING_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("SETUP_TOKEN", "test-setup-token")
    app = create_app({"TESTING": True, "TRUSTED_PROXIES": 1, "SESSION_COOKIE_SECURE": True, "SESSION_COOKIE_NAME": "__Host-teamudvikling"})
    app.edge = Edge(app)
    return app


@pytest.fixture
def world(prod):
    """Admin + holdet + træneren 'anna' (med 2FA), alt oprettet via den 'rigtige' vej (Cloudflare-lignende headers)."""
    a = Client(prod)
    a.post("/setup", {"username": "admin", "display_name": "Admin", "password": PW, "password2": PW}, page="/setup")
    page = a.get("/2fa/setup").get_data(as_text=True)
    a.secret = re.search(r'class="secret">([A-Z2-7]+)<', page).group(1)
    a.post("/2fa/setup", {"code": totp.totp(a.secret)}, page="/2fa/setup")
    make_team(a, "Hold Alfa")
    anna = make_trainer(prod, a, "anna", ["Hold Alfa"])
    return prod, a, anna


def sql(app, q, *a):
    con = appdb.connect(app.config["DATABASE"])
    rows = con.execute(q, a).fetchall()
    con.commit()
    con.close()
    return rows


def login_as(app, name, pw, secret):
    sql(app, "UPDATE users SET last_totp_step=0 WHERE username=?", name)
    c = Client(app)
    return c, c.login(name, pw, secret=secret)


def bad_login(app, user, pw="forkert-forkert-12", ip=None):
    if ip:
        app.edge.ip = ip
    c = Client(app)
    c.c.get("/login")
    return c.post("/login", {"username": user, "password": pw}, page="/login")


def ok_session(resp_client):
    return resp_client.get("/?hold=1").status_code == 200


# ------------------------------------------------------------------ 1. IP-spoofing mod login-spærren
def test_spoofed_xff_cannot_evade_ip_throttle(world):
    app, _, _ = world
    app.edge.ip = "198.51.100.7"
    codes = []
    for i in range(30):
        app.edge.spoof = f"10.{i}.{i}.1"                  # angriberen roterer en falsk 'klient-IP' først i kæden
        codes.append(bad_login(app, f"ukendt{i}").status_code)
    assert 429 in codes


# ------------------------------------------------------------------ 2. Lås-DoS: angriber låser trænerens konto
def test_attacker_cannot_lock_out_the_real_user(world):
    app, _, anna = world
    for _ in range(6):
        bad_login(app, "anna", ip="198.51.100.7")           # angriber
    app.edge.ip = "192.0.2.55"                              # træneren, anden forbindelse
    c, r = login_as(app, "anna", PW, anna.secret)
    assert r.status_code == 302 and ok_session(c)


def test_attacker_ip_stays_locked_even_with_correct_password(world):
    app, _, anna = world
    for _ in range(6):
        bad_login(app, "anna", ip="198.51.100.7")
    c, r = login_as(app, "anna", PW, anna.secret)           # stadig angriberens IP
    assert not (r.status_code == 302 and ok_session(c))


def test_distributed_attack_still_locks_account_globally(world):
    app, _, anna = world
    for n in range(8):                                      # mange IP'er, 5 forsøg hver = over den samlede grænse
        for _ in range(5):
            bad_login(app, "anna", ip=f"198.51.100.{n + 10}")
    app.edge.ip = "192.0.2.55"
    c, r = login_as(app, "anna", PW, anna.secret)
    assert not (r.status_code == 302 and ok_session(c))


# ------------------------------------------------------------------ 3. Brugeropremsning via svar og tid
def test_same_response_for_unknown_wrong_and_locked(world):
    app, _, _ = world
    for _ in range(6):
        bad_login(app, "anna", ip="198.51.100.7")           # anna er nu låst for angriberen
    app.edge.ip = "198.51.100.7"
    bodies = {}
    for name in ("anna", "findes-ikke", "admin"):
        r = bad_login(app, name)
        bodies[name] = (r.status_code, re.sub(r'value="[^"]+"', "", r.get_data(as_text=True)))
    assert len({v for v in bodies.values()}) == 1, bodies


def test_no_timing_oracle_for_locked_accounts(world):
    app, _, _ = world
    for _ in range(5):
        bad_login(app, "anna", ip="198.51.100.7")           # lås (for denne IP)

    def sample(user, ip):
        app.edge.ip = ip
        out = []
        for _ in range(4):
            c = Client(app)
            c.c.get("/login")
            tok = c.token("/login")
            t = time.perf_counter()
            c.c.post("/login", data={"username": user, "password": "forkert-forkert-12", "csrf_token": tok})
            out.append(time.perf_counter() - t)
        return statistics.median(out)

    locked = sample("anna", "198.51.100.7")
    unknown = sample("findes-ikke", "198.51.100.8")
    wrong = sample("admin", "198.51.100.9")
    assert locked > 0.4 * unknown and locked > 0.4 * wrong, (locked, unknown, wrong)


# ------------------------------------------------------------------ 4. Sessioner
def test_session_cookie_dies_on_logout(world):
    app, _, anna = world
    c, r = login_as(app, "anna", PW, anna.secret)
    assert ok_session(c)
    stolen = c.c.get_cookie("__Host-teamudvikling").value             # kopieret cookie
    c.post("/logout", {}, page="/account")
    replay = app.test_client()
    replay.set_cookie("__Host-teamudvikling", stolen)
    r = replay.get("/?hold=1")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_forged_or_tampered_session_is_anonymous(world):
    app, _, anna = world
    c, _ = login_as(app, "anna", PW, anna.secret)
    good = c.c.get_cookie("__Host-teamudvikling").value
    for bad in (good[:-3] + ("AAA" if not good.endswith("AAA") else "BBB"), "x" + good, ".".join(["e30", "AAAAAA", "BBBB"]), "garbage"):
        cl = app.test_client()
        cl.set_cookie("__Host-teamudvikling", bad)
        r = cl.get("/players/")
        assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_cookie_flags_in_production(world):
    app, _, _ = world
    c = Client(app)
    r = c.c.get("/login")
    ck = [h for h in r.headers.getlist("Set-Cookie") if h.startswith("__Host-teamudvikling=")][0]
    low = ck.lower()
    assert "secure" in low and "httponly" in low and "samesite=lax" in low and "path=/" in low and "domain=" not in low


# ------------------------------------------------------------------ 5. 2FA
def test_totp_code_cannot_be_used_twice_concurrently(world):
    app, _, anna = world
    from app import auth
    uid = sql(app, "SELECT id FROM users WHERE username='anna'")[0]["id"]
    con = appdb.connect(app.config["DATABASE"])
    step = totp.step_at()
    con.execute("UPDATE users SET last_totp_step=0 WHERE id=?", (uid,))
    con.commit()
    assert auth.consume_totp_step(con, uid, step) is True      # to samtidige forespørgsler, begge med samme læste tilstand
    assert auth.consume_totp_step(con, uid, step) is False     # den anden må ikke også lykkes
    con.close()


def test_2fa_bruteforce_is_stopped(world):
    app, _, anna = world
    sql(app, "UPDATE users SET last_totp_step=0 WHERE username='anna'")
    app.edge.ip = "198.51.100.7"
    c = Client(app)
    c.c.get("/login")
    c.post("/login", {"username": "anna", "password": PW}, page="/login")
    for guess in ("000000", "111111", "222222", "333333", "444444", "555555", "666666"):
        c.post("/login/2fa", {"code": guess}, page="/login/2fa")
    r = c.post("/login/2fa", {"code": totp.totp(anna.secret)}, page="/login/2fa")
    assert not (r.status_code == 302 and ok_session(c))


# ------------------------------------------------------------------ 6. Redirects, CSRF, input
@pytest.mark.parametrize("nxt", ["//evil.example", "/\\evil.example", "https://evil.example", "javascript:alert(1)", "%2F%2Fevil.example",
                                 "/\t/evil.example", "///evil.example", "\\\\evil.example", "/%5Cevil.example"])
def test_no_open_redirect_after_login(world, nxt):
    app, _, anna = world
    sql(app, "UPDATE users SET last_totp_step=0 WHERE username='anna'")
    c = Client(app)
    c.c.get("/login")
    r = c.post(f"/login?next={nxt}", {"username": "anna", "password": PW}, page="/login")
    r = c.post("/login/2fa", {"code": totp.totp(anna.secret)}, page="/login/2fa")
    loc = r.headers.get("Location", "")
    assert r.status_code == 302 and loc.startswith("/") and not loc.startswith("//") and "\\" not in loc and "evil" not in loc


def test_login_requires_valid_csrf(world):
    app, _, _ = world
    c = Client(app)
    assert c.c.post("/login", data={"username": "anna", "password": PW}).status_code == 400
    other = Client(app)
    tok = other.token("/login")                              # token fra en anden session
    assert c.c.post("/login", data={"username": "anna", "password": PW, "csrf_token": tok}).status_code == 400


def test_huge_inputs_rejected_quickly(world):
    app, _, _ = world
    c = Client(app)
    c.c.get("/login")
    t = time.perf_counter()
    r = c.post("/login", {"username": "a" * 100_000, "password": "p" * 500_000}, page="/login")
    assert time.perf_counter() - t < 3
    assert r.status_code in (200, 400, 413) and "dashboard" not in r.get_data(as_text=True).lower()


# ------------------------------------------------------------------ 7. Hoveder og informationslækage
def test_login_page_headers_and_no_info_leak(world):
    app, _, _ = world
    r = Client(app).c.get("/login")
    h = r.headers
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"] and "script-src 'self'" in h["Content-Security-Policy"]
    assert h["X-Frame-Options"] == "DENY" and h["X-Content-Type-Options"] == "nosniff"
    assert "no-store" in h["Cache-Control"] and "max-age" in h["Strict-Transport-Security"]
    assert "noindex" in h.get("X-Robots-Tag", "")                                    # ingen søgemaskine-indeksering
    body = r.get_data(as_text=True)
    assert f"v{app.config['VERSION']}" not in body                                    # ingen versionsnummer til anonyme
    assert "<script" not in body.lower().replace('<script src="/static/', "")        # ingen indlejret script


def test_errors_do_not_leak(world):
    app, _, _ = world
    c = Client(app)
    for method, path in (("GET", "/findes-ikke"), ("POST", "/login/2fa"), ("PUT", "/login"), ("DELETE", "/"), ("TRACE", "/login")):
        r = c.c.open(path, method=method)
        txt = r.get_data(as_text=True)
        assert "Traceback" not in txt and "werkzeug" not in txt.lower() and "sqlite" not in txt.lower(), (method, path)


def test_warns_when_secure_cookies_without_proxy_trust(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("TEAMUDVIKLING_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SETUP_TOKEN", "x")
    import logging
    with caplog.at_level(logging.WARNING):
        create_app({"TESTING": True, "SESSION_COOKIE_SECURE": True, "TRUSTED_PROXIES": 0})
    assert any("TRUSTED_PROXIES" in r.getMessage() for r in caplog.records)
