"""Sikkerhedsgennemgang 3 (v0.29.0): åben omdirigering i sprogvalg, DNS-rebinding i kalenderhentning, begrænsning af udgående kald, billedformater."""
import io
import socket

import pytest
from PIL import Image

from app import ical, photos
from helpers import team_id
from test_clubs_invites import make_user, mailapp, sql, world  # noqa: F401


@pytest.mark.parametrize("bad", ["/\t/evil.example", "/\n/evil.example", "/\\evil.example", "//evil.example", "https://evil.example", "/\r/evil"])
def test_language_next_cannot_redirect_off_site(app, admin, bad):
    r = admin.post("/sprog", {"lang": "en", "next": bad}, page="/")
    assert r.status_code == 302 and r.headers["Location"] in ("/", "http://localhost/")


def test_ical_dns_rebinding_is_blocked_and_connection_is_pinned(monkeypatch):
    answers = iter(["93.184.216.34", "127.0.0.1"])                     # 1. opslag offentligt, 2. opslag internt (rebinding)
    monkeypatch.setattr(ical.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", (next(answers), 443))])
    used = []
    monkeypatch.setattr(ical.socket, "create_connection", lambda addr, *a, **k: used.append(addr) or (_ for _ in ()).throw(OSError("stop")))
    with pytest.raises(ical.FeedError):
        ical.fetch("https://kalender.example/a.ics")
    assert used == []                                                    # ingen forbindelse til nogen adresse


def test_ical_connects_to_the_checked_ip(monkeypatch):
    monkeypatch.setattr(ical.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    used = []
    def fake(addr, *a, **k):
        used.append(addr)
        raise OSError("stop")
    monkeypatch.setattr(ical.socket, "create_connection", fake)
    with pytest.raises(ical.FeedError):
        ical.fetch("https://kalender.example/a.ics")
    assert used == [("93.184.216.34", 443)]


def test_ical_url_with_control_characters_is_rejected(monkeypatch):
    monkeypatch.setattr(ical.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    for bad in ("https://x.example/a b.ics", "https://x.example/a\r\nHost: y.ics", "https://x.example/\ta.ics"):
        with pytest.raises(ical.FeedError):
            ical.check_url(bad)


def test_match_suggestions_throttle_outgoing_fetches(world, monkeypatch):
    app, admin, ca, cb, ta, tb = world
    calls = []
    monkeypatch.setattr(ical, "fetch", lambda url: calls.append(url) or "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")
    tid = team_id(app, "Hold Alfa")
    sql(app, "INSERT INTO settings(key,value) VALUES(?,?)", f"t{tid}:ical_url", "https://x.example/a.ics")
    for _ in range(5):
        assert ta.get("/kampe/forslag").status_code == 200
    assert len(calls) == 1                                               # én hentning pr. minut pr. hold


@pytest.mark.parametrize("fmt", ["BMP", "TIFF", "GIF", "ICO"])
def test_photo_parsers_for_other_formats_are_never_used(fmt):
    buf = io.BytesIO()
    Image.new("RGB", (100, 100)).save(buf, fmt)
    with pytest.raises(photos.PhotoError):
        photos.process(buf.getvalue())
    with pytest.raises(photos.PhotoError):
        photos.process_free(buf.getvalue())
