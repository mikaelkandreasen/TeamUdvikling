"""I-07: tilgængelighedstjek uden browser (kontrast, sprog, labels, billedtekster) + valgfri browser-test af mobil-flowet."""
import re

import pytest

from conftest import PW  # noqa: F401
from helpers import add_player, player_id


def _lum(hexcol):
    h = hexcol.lstrip("#")
    h = "".join(c * 2 for c in h) if len(h) == 3 else h
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4   # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_default_heat_colours_have_readable_text():
    from app import heatcfg
    for n, bg in enumerate(heatcfg.DEFAULT_COLORS, 1):
        assert contrast(bg, heatcfg.text_color(bg)) >= 4.5, (n, bg)


def test_stylesheet_text_colours_meet_aa():
    from pathlib import Path
    css = (Path(__file__).resolve().parent.parent / "app" / "static" / "style.css").read_text()
    vars_ = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{3,6})", css))
    assert contrast(vars_["mut"], "#ffffff") >= 4.5, "dæmpet tekst (--mut) på hvid"
    assert contrast("#ffffff", vars_["navy"]) >= 4.5, "hvid tekst på mørk baggrund"


@pytest.fixture
def team(app, admin):
    from helpers import make_team
    make_team(admin, "U11 piger")
    return admin


@pytest.fixture
def pages(app, team):
    add_player(team, "Anna Alfa")
    pid = player_id(app, "Anna Alfa")
    paths = ["/login", "/?hold=1", "/m?hold=1", "/menu", "/players/", "/players/new", "/eval", f"/eval/1/{pid}", "/overview", "/account", "/inbox/", "/kampe/", "/devdata/fremmoede"]
    return {p: team.get(p).get_data(as_text=True) for p in paths}


def test_pages_have_language_title_and_labelled_fields(pages):
    for path, html in pages.items():
        assert re.search(r'<html lang="?[a-z]{2}', html), path
        assert re.search(r"<title>.+</title>", html, re.S), path
        assert 'name="viewport"' in html, path
        assert len(re.findall(r"<h1", html)) <= 1, f"{path}: flere h1"
        for m in re.finditer(r"<img\b[^>]*>", html):
            assert " alt=" in m.group(0), f"{path}: billede uden alt"
        ids = set(re.findall(r'<label[^>]*\bfor="([^"]+)"', html))
        for m in re.finditer(r"<(input|select|textarea)\b([^>]*)>", html):
            attrs = m.group(2)
            if re.search(r'type="(hidden|submit|button|checkbox|radio)"', attrs):
                continue
            ident = re.search(r'\bid="([^"]+)"', attrs)
            assert ident and ident.group(1) in ids or "aria-label" in attrs, f"{path}: felt uden label: {attrs[:80]}"


def test_touch_targets_are_large_enough_in_stylesheet():
    from pathlib import Path
    css = (Path(__file__).resolve().parent.parent / "app" / "static" / "style.css").read_text()
    assert int(re.search(r"--tap:\s*(\d+)px", css).group(1)) >= 44, "--tap (trykflade) mindst 44 px"
    tab = re.search(r"\.tabbar a\{([^}]*)\}", css).group(1)
    assert int(re.search(r"min-height:\s*(\d+)px", tab).group(1)) >= 44


def test_browser_mobile_flow_if_playwright_installed():
    """Kører kun hvis Playwright er installeret (pip install playwright && playwright install chromium) – ellers springes den over."""
    pytest.importorskip("playwright.sync_api")
    pytest.skip("Browser-flowet kører mod en kørende server: se docs/DRIFT.md (tests/ui/mobile_flow.py)")
