"""Sprogvalg: dansk som standard; engelsk, tysk, svensk og norsk; cookie + gemt på brugeren; alle brugte tekster er oversat."""
import pathlib
import re

import pytest

from app import i18n
from conftest import Client


def test_default_is_danish_and_cookie_switches_login_page(app, admin):
    c = Client(app)
    page = c.get("/login").get_data(as_text=True)
    assert 'lang="da"' in page and "Brugernavn" in page
    r = c.post("/sprog", {"lang": "de", "next": "/login"}, page="/login")
    assert r.status_code == 302 and "lang=de" in r.headers["Set-Cookie"]
    page = c.get("/login").get_data(as_text=True)
    assert 'lang="de"' in page and "Benutzername" in page and "Passwort" in page
    assert "Brugernavn" not in page


def test_invalid_language_and_open_redirect_are_rejected(app, admin):
    c = Client(app)
    assert c.post("/sprog", {"lang": "xx"}, page="/login").status_code == 400
    for bad in ("https://evil.example", "//evil.example", "/\\evil"):
        r = c.post("/sprog", {"lang": "en", "next": bad}, page="/login")
        assert r.headers["Location"].endswith("/") and "evil" not in r.headers["Location"]


def test_language_is_saved_on_user_and_follows_to_other_browser(admin, app):
    admin.post("/sprog", {"lang": "sv", "next": "/"}, page="/")
    from app import db
    con = db.connect(app.config["DATABASE"])
    assert con.execute("SELECT lang FROM users WHERE username='admin'").fetchone()[0] == "sv"
    con.close()
    page = admin.get("/account").get_data(as_text=True)
    assert "Byt lösenord" in page and "Mitt konto" in page
    admin.c.delete_cookie("lang")                                   # ny browser uden cookie: brugerens gemte sprog bruges
    assert "Byt lösenord" in admin.get("/account").get_data(as_text=True)
    admin.post("/sprog", {"lang": "da", "next": "/"}, page="/")
    assert "Skift adgangskode" in admin.get("/account").get_data(as_text=True)


def test_every_translation_is_complete():
    for k, v in i18n._T.items():
        assert len(v) == 4 and all(x.strip() for x in v), k
    assert set(i18n.TR) == {"en", "de", "sv", "no"} and set(i18n.LANGS) == {"da", "en", "de", "sv", "no"}


def test_every_text_marked_for_translation_in_templates_exists():
    """Tekster i {{ _('…') }} skal findes i oversættelsestabellen (ellers vises de på dansk i alle sprog)."""
    root = pathlib.Path(__file__).resolve().parent.parent / "app" / "templates"
    used = set()
    for f in root.glob("*.html"):
        used |= {m.group(2) for m in re.finditer(r"""_\((['"])(.+?)\1\)""", f.read_text())}
    missing = sorted(used - set(i18n._T))
    assert used and not missing, missing
