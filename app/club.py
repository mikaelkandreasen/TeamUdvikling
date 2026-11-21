"""Klubprofil pr. klub: navn, kontaktinfo, rapport-fodtekst, farve og logo (alle hold i klubben bruger klubbens udseende).

Logoet gemmes i databasen (clubs.logo) og serves af `main.club_logo` (offentligt, så det kan vises på loginsiden).
Kun PNG, JPEG og WebP accepteres (indhold tjekkes, ikke filnavn). SVG afvises bevidst (kan indeholde scripts).
"""
import re
import time

from flask import current_app, g, url_for

from .db import club_get, get_db

MAX_LOGO_BYTES = 512 * 1024
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def sniff_image(data):
    """Returnerer MIME-type ud fra filens indhold, ellers None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def contrast_with_white(hexcolor):
    r, g, b = (int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))
    lum = 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)
    return 1.05 / (lum + 0.05)


def shade(hexcolor, factor):
    r, g, b = (int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(c * factor))) for c in (r, g, b))


def valid_color(value):
    """None hvis gyldig; ellers en fejltekst. Hvid tekst skal kunne læses på farven (kontrast ≥ 4,5)."""
    if not value:
        return None
    if not HEX.match(value):
        return "Farven skal angives som #RRGGBB."
    if contrast_with_white(value) < 4.5:
        return "Vælg en mørkere farve, så hvid tekst kan læses på den."
    return None


def save_logo(db, club_id, data):
    """Gemmer klubbens logo i databasen. Returnerer None ved succes, ellers fejltekst."""
    if not data:
        return "Vælg en billedfil."
    if len(data) > MAX_LOGO_BYTES:
        return "Logoet må højst fylde 512 kB."
    mime = sniff_image(data)
    if not mime:
        return "Logoet skal være PNG, JPEG eller WebP."
    db.execute("UPDATE clubs SET logo=?, logo_mime=?, logo_v=? WHERE id=?", (data, mime, str(int(time.time())), club_id))
    return None


def remove_logo(db, club_id):
    db.execute("UPDATE clubs SET logo=NULL, logo_mime='', logo_v='' WHERE id=?", (club_id,))


def current_club_id():
    """Hvilken klubs udseende der vises: det aktive holds klub, ellers brugerens klub, ellers standardklubben."""
    if g.get("team") is not None and g.team["club_id"]:
        return g.team["club_id"]
    if g.get("user") is not None and g.user["club_id"]:
        return g.user["club_id"]
    return None


def info():
    """Klubprofil til skabeloner (cachet pr. request)."""
    if "club_info" in g:
        return g.club_info
    c = club_get(get_db(), current_club_id())
    has_logo = bool(c["logo_mime"])
    color = c["color"] if HEX.match(c["color"] or "") else ""
    g.club_info = dict(c, has_logo=has_logo, logo_url=url_for("main.club_logo", cid=c["id"], v=c["logo_v"]) if has_logo else "",
                       color=color, dark=shade(color, 0.72) if color else "")
    return g.club_info
