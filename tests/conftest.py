import os
import re

import pytest

from app import create_app, totp

PW = "correct-horse-battery-12"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("U11_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("SETUP_TOKEN", raising=False)
    return create_app({"TESTING": True})


class Client:
    """Tynd wrapper om Flask-testklienten med CSRF-håndtering og login med 2FA."""

    def __init__(self, app):
        self.app = app
        self.c = app.test_client()
        self.secret = None

    def token(self, path="/login"):
        html = self.c.get(path, follow_redirects=True).get_data(as_text=True)
        m = re.search(r'name="csrf_token" value="([^"]+)"', html)
        return m.group(1) if m else None

    def post(self, path, data=None, page=None, **kw):
        data = dict(data or {})
        data["csrf_token"] = self.token(page or path)
        return self.c.post(path, data=data, **kw)

    def get(self, path, **kw):
        return self.c.get(path, **kw)

    def login(self, username, password=PW, secret=None):
        self.c.get("/login")
        r = self.post("/login", {"username": username, "password": password}, page="/login")
        if r.status_code != 302:
            return r
        if "/2fa/setup" in r.headers["Location"]:
            page = self.get("/2fa/setup").get_data(as_text=True)
            self.secret = re.search(r'class="secret">([A-Z2-7]+)<', page).group(1)
            r = self.post("/2fa/setup", {"code": totp.totp(self.secret)}, page="/2fa/setup")
            return r
        secret = secret or self.secret
        r = self.post("/login/2fa", {"code": totp.totp(secret)}, page="/login/2fa")
        return r


@pytest.fixture
def client(app):
    return Client(app)


@pytest.fixture
def admin(app):
    c = Client(app)
    c.post("/setup", {"username": "admin", "display_name": "Admin", "password": PW, "password2": PW}, page="/setup")
    # setup logger ind i stage needs_setup → gennemfør 2FA-opsætning
    page = c.get("/2fa/setup").get_data(as_text=True)
    c.secret = re.search(r'class="secret">([A-Z2-7]+)<', page).group(1)
    c.post("/2fa/setup", {"code": totp.totp(c.secret)}, page="/2fa/setup")
    return c
