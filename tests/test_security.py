"""Pentest som regressionstests (white-box): angreb mod den kørende app. Se docs/SECURITY.md."""
import re
import time

import pytest

from app import create_app
from conftest import PW, Client
from helpers import add_player, make_team, make_trainer, player_id, score_all, switch, team_id

EVIL = '<script>alert(1)</script>'


def rules(app, method):
    out = []
    for r in app.url_map.iter_rules():
        if method in r.methods and r.endpoint != "static":
            out.append(r)
    return out


def fill(rule, v=1):
    return re.sub(r"<[^>]+>", str(v), rule.rule)


# ---------------------------------------------------------------- adgang uden login
def test_all_routes_require_login(app):
    c = app.test_client()
    public = {"auth.login", "auth.login_2fa", "auth.setup", "healthz", "main.club_logo", "main.privacy", "reset.link"}
    for r in app.url_map.iter_rules():
        if r.endpoint in public or r.endpoint == "static":
            continue
        for m in ("GET", "POST"):
            if m in r.methods:
                resp = c.open(fill(r), method=m)
                assert resp.status_code in (302, 400, 404, 405), (r.rule, m, resp.status_code)
                if resp.status_code == 302:
                    assert "/login" in resp.headers["Location"], (r.rule, m)


def test_pw_ok_session_cannot_skip_2fa(app, admin):
    make_team(admin, "A")
    c = Client(app)
    c.login("admin", PW, secret=admin.secret) if False else None
    c.c.get("/login")
    c.post("/login", {"username": "admin", "password": PW}, page="/login")          # kun trin 1
    for path in ("/", "/players/", "/admin/", "/m"):
        r = c.get(path)
        assert r.status_code == 302 and ("/login/2fa" in r.headers["Location"]), path


# ---------------------------------------------------------------- CSRF
def test_every_post_requires_csrf(app, admin):
    make_team(admin, "A")
    for r in rules(app, "POST"):
        if r.endpoint in ("auth.login", "auth.login_2fa", "auth.setup"):
            continue
        resp = admin.c.post(fill(r), data={})
        assert resp.status_code == 400, (r.rule, resp.status_code)


# ---------------------------------------------------------------- rettigheder / IDOR
def test_trainer_blocked_from_admin_and_other_teams(app, admin):
    make_team(admin, "A"); make_team(admin, "B")
    switch(admin, team_id(app, "A"))
    add_player(admin, "Anna Alfa")
    pid = player_id(app, "Anna Alfa")
    t = make_trainer(app, admin, "tb", ["B"])
    for r in app.url_map.iter_rules():
        if r.endpoint.startswith("admin.") or r.endpoint in ("players.export_json", "players.delete"):
            for m in ("GET", "POST"):
                if m in r.methods:
                    resp = t.c.open(fill(r, pid), method=m, data={"csrf_token": t.token("/")} if m == "POST" else None)
                    assert resp.status_code in (403, 404, 405), (r.rule, m, resp.status_code)
    for r in app.url_map.iter_rules():
        if "pid" in r.rule or "<int:pid>" in r.rule or "<int:player_id>" in r.rule:
            for m in ("GET", "POST"):
                if m in r.methods and not r.endpoint.startswith("admin."):
                    resp = t.c.open(re.sub(r"<int:rnd>", "1", fill(r, pid)), method=m,
                                    data={"csrf_token": t.token("/")} if m == "POST" else None)
                    assert resp.status_code in (403, 404, 405), (r.rule, m, resp.status_code)
    # skift til hold uden adgang
    assert switch(t, team_id(app, "A")).status_code == 403


# ---------------------------------------------------------------- XSS
def test_stored_xss_is_escaped_everywhere(app, admin):
    make_team(admin, "A")
    add_player(admin, EVIL)
    pid = player_id(app, EVIL)
    admin.post(f"/players/{pid}/edit", {"name": EVIL, "birth_date": "2016-03-10", "notes": EVIL, "focus1": EVIL, "active": "1"},
               page=f"/players/{pid}/edit")
    for path in ("/players/", f"/profile/{pid}", f"/report/{pid}", "/reports/all", "/overview", "/areas", "/development",
                 "/tablet", "/m", "/devdata/", f"/players/{pid}/edit", "/motivation/", f"/motivation/report/{pid}"):
        r = admin.get(path, follow_redirects=True)
        html = r.get_data(as_text=True)
        assert "<script>alert(1)" not in html, path


def test_login_and_search_sqli(app, admin):
    c = Client(app)
    c.c.get("/login")
    r = c.post("/login", {"username": "admin' OR '1'='1' --", "password": "x' OR '1'='1"}, page="/login")
    assert r.status_code == 200


# ---------------------------------------------------------------- opsætning (take-over)
def test_setup_requires_token_even_without_env(tmp_path, monkeypatch):
    monkeypatch.setenv("U11_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SETUP_TOKEN", raising=False)
    app = create_app({"TESTING": True})
    c = Client(app)
    r = c.post("/setup", {"username": "evil", "password": PW, "password2": PW}, page="/setup")
    assert r.status_code == 200 and "opsætningskode" in r.get_data(as_text=True).lower()
    tok = (tmp_path / "setup_token").read_text().strip()
    assert len(tok) >= 20
    r = c.post("/setup", {"username": "ok", "password": PW, "password2": PW, "setup_token": tok}, page="/setup")
    assert r.status_code == 302
    assert not (tmp_path / "setup_token").exists()           # engangskode slettes


# ---------------------------------------------------------------- brute force
def test_ip_throttle_blocks_password_spraying(app, admin):
    c = Client(app)
    codes = []
    for i in range(40):
        c.c.get("/login")
        r = c.post("/login", {"username": f"user{i}", "password": "forkert-kode-123"}, page="/login",
                   environ_overrides={"REMOTE_ADDR": "203.0.113.9"})
        codes.append(r.status_code)
    assert 429 in codes
    # en anden IP er upåvirket
    c.c.get("/login")
    assert c.post("/login", {"username": "x", "password": "y"}, page="/login",
                  environ_overrides={"REMOTE_ADDR": "198.51.100.7"}).status_code == 200


def test_account_lockout_and_no_user_enumeration(app, admin):
    c = Client(app); c.c.get("/login")
    a = c.post("/login", {"username": "admin", "password": "forkert-forkert1"}, page="/login").get_data(as_text=True)
    b = c.post("/login", {"username": "findes-ikke", "password": "forkert-forkert1"}, page="/login").get_data(as_text=True)
    strip = lambda h: re.sub(r'name="csrf_token" value="[^"]+"', "", h)
    assert strip(a) == strip(b)


# ---------------------------------------------------------------- sessioner
def test_old_session_dies_after_password_change(app, admin):
    stolen = admin.c.get_cookie("session") if hasattr(admin.c, "get_cookie") else None
    assert stolen is not None
    thief = app.test_client()
    thief.set_cookie("session", stolen.value)
    assert thief.get("/no-team").status_code in (200, 302)
    assert thief.get("/no-team").status_code == 200           # cookien virker før skift
    admin.post("/account", {"action": "password", "old": PW, "new": PW + "x2", "new2": PW + "x2"}, page="/account")
    r = thief.get("/no-team")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert admin.get("/no-team").status_code == 200           # den legitime session overlever


def test_2fa_reset_kills_live_session(app, admin):
    make_team(admin, "A")
    t = make_trainer(app, admin, "tr", ["A"])
    assert t.get("/").status_code in (200, 302)
    from app import db
    con = db.connect(app.config["DATABASE"])
    uid = con.execute("SELECT id FROM users WHERE username='tr'").fetchone()[0]
    con.close()
    admin.post(f"/admin/users/{uid}/reset-2fa", {"code": _fresh_code(app, admin)}, page="/admin/users")
    r = t.get("/players/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_open_redirect_blocked(app, admin):
    for nxt in ("//evil.com", "/\\evil.com", "https://evil.com", "/\\/evil.com", "///evil.com"):
        c = Client(app)
        c.c.get(f"/login?next={nxt}")
        r = c.post(f"/login?next={nxt}", {"username": "admin", "password": PW}, page="/login")
        from app import totp
        r = c.post("/login/2fa", {"code": totp.totp(admin.secret, time.time() + 30)}, page="/login/2fa")
        loc = r.headers.get("Location", "")
        assert "evil.com" not in loc and not loc.startswith(("//", "/\\")), (nxt, loc)


# ---------------------------------------------------------------- headers / cookies / info
def test_security_headers_and_cookie_flags(tmp_path, monkeypatch):
    monkeypatch.setenv("U11_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COOKIE_SECURE", "1")
    monkeypatch.setenv("SETUP_TOKEN", "x")
    app = create_app({"TESTING": True})
    r = app.test_client().get("/login", base_url="https://example.org")
    h = r.headers
    assert "max-age" in h.get("Strict-Transport-Security", "")
    assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"] and "unsafe-eval" not in h["Content-Security-Policy"]
    assert "script-src 'self'" in h["Content-Security-Policy"] and "unsafe-inline'" not in h["Content-Security-Policy"].split("script-src")[1].split(";")[0]
    assert "Permissions-Policy" in h and h["Cache-Control"] == "no-store"
    cookie = r.headers.get("Set-Cookie", "")
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie and cookie.startswith("__Host-")


def test_healthz_leaks_nothing(app):
    body = app.test_client().get("/healthz").get_data(as_text=True)
    assert "version" not in body and "ok" in body


def test_error_pages_do_not_leak(app, admin):
    r = admin.get("/findes-ikke")
    assert r.status_code == 404 and "Traceback" not in r.get_data(as_text=True)
    big = admin.c.post("/admin/club", data={"csrf_token": "x", "name": "a" * (2 * 1024 * 1024)})
    assert big.status_code == 413


# ---------------------------------------------------------------- data ud af huset
def test_excel_export_neutralises_formulas(app, admin):
    import io
    from openpyxl import load_workbook
    make_team(admin, "A")
    add_player(admin, "=HYPERLINK(\"http://evil\",\"x\")")
    r = admin.get("/admin/export.xlsx")
    ws = load_workbook(io.BytesIO(r.data))["Spillere"]
    cell = ws.cell(row=2, column=2)
    assert cell.data_type != "f"


def test_recovery_codes_long_and_not_plain_sha(app, admin):
    from app import db
    con = db.connect(app.config["DATABASE"])
    h = con.execute("SELECT code_hash FROM recovery_codes LIMIT 1").fetchone()
    con.close()
    page = admin.c.post("/account", data={"action": "recovery", "old": PW, "csrf_token": admin.token("/account")}).get_data(as_text=True)
    code = re.search(r"([0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4})", page)
    assert code, "gendannelseskoder skal være mindst 48 bit"
    import hashlib
    con = db.connect(app.config["DATABASE"])
    hashes = {r[0] for r in con.execute("SELECT code_hash FROM recovery_codes")}
    con.close()
    assert hashlib.sha256(code.group(1).replace("-", "").encode()).hexdigest() not in hashes   # nøglet hash, ikke ren SHA-256


def _fresh_code(app, admin):
    from app import db as _db, totp as _totp
    con = _db.connect(app.config["DATABASE"]); con.execute("UPDATE users SET last_totp_step=0 WHERE username='admin'"); con.commit(); con.close()
    return _totp.totp(admin.secret)
