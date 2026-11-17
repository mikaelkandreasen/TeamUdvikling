"""Klubprofil: navn, kontaktinfo, rapport-fodtekst, farve og logo (gælder alle hold).

Logoet gemmes som fil i /data/branding og serves af `main.club_logo` (offentligt, så det kan vises på loginsiden).
Kun PNG, JPEG og WebP accepteres (indhold tjekkes, ikke filnavn). SVG afvises bevidst (kan indeholde scripts).
"""
import os
import re
import time

from flask import current_app, g, url_for

from .db import club_get, club_set, get_db

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


def logo_path():
    return os.path.join(current_app.config["U11_DATA_DIR"], "branding", "logo.bin")


def save_logo(db, data):
    """Gemmer logo. Returnerer None ved succes, ellers fejltekst."""
    if not data:
        return "Vælg en billedfil."
    if len(data) > MAX_LOGO_BYTES:
        return "Logoet må højst fylde 512 kB."
    mime = sniff_image(data)
    if not mime:
        return "Logoet skal være PNG, JPEG eller WebP."
    os.makedirs(os.path.dirname(logo_path()), exist_ok=True)
    with open(logo_path(), "wb") as f:
        f.write(data)
    club_set(db, "logo_mime", mime)
    club_set(db, "logo_v", str(int(time.time())))
    return None


def remove_logo(db):
    try:
        os.remove(logo_path())
    except FileNotFoundError:
        pass
    club_set(db, "logo_mime", "")
    club_set(db, "logo_v", "")


def info():
    """Klubprofil til skabeloner (cachet pr. request)."""
    if "club_info" in g:
        return g.club_info
    c = club_get(get_db())
    has_logo = bool(c["logo_mime"]) and os.path.exists(logo_path())
    color = c["color"] if HEX.match(c["color"] or "") else ""
    g.club_info = dict(c, has_logo=has_logo, logo_url=url_for("main.club_logo", v=c["logo_v"]) if has_logo else "",
                       color=color, dark=shade(color, 0.72) if color else "")
    return g.club_info
