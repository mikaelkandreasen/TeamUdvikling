import io
import struct
import zlib

import pytest

from helpers import add_player, make_team, make_trainer, player_id


def png_bytes():
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = zlib.compress(b"\x00\xff\x00\x00")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


def save(admin, **fields):
    data = {"action": "save", "name": "", "address": "", "email": "", "phone": "", "website": "", "footer": "", "color": ""}
    data.update({k: v for k, v in fields.items() if k != "logo"})
    data["csrf_token"] = admin.token("/admin/club")
    if "logo" in fields:
        data["logo"] = (io.BytesIO(fields["logo"][1]), fields["logo"][0])
    return admin.c.post("/admin/club", data=data, content_type="multipart/form-data", follow_redirects=True)


@pytest.fixture
def team(app, admin):
    make_team(admin, "U11 piger")
    return admin


def test_profile_text_color_and_footer_show_up(app, team):
    add_player(team, "Anna Alfa")
    r = save(team, name="Virring Fodbold", address="Virringvej 1", email="u11@klub.dk", footer="Kontakt trænerne", color="#14532d")
    assert "Klubprofilen er gemt" in r.get_data(as_text=True)
    page = team.get("/").get_data(as_text=True)
    assert "--navy2:#14532d" in page and "Virring Fodbold" in page
    rep = team.get("/report/%d" % player_id(app, "Anna Alfa")).get_data(as_text=True)
    assert "Virringvej 1" in rep and "Kontakt trænerne" in rep


def test_logo_upload_served_publicly_and_removable(app, team):
    assert team.get("/branding/logo/1").status_code == 404
    save(team, name="Klub", logo=("logo.png", png_bytes()))
    r = team.get("/branding/logo/1")
    assert r.status_code == 200 and r.mimetype == "image/png" and r.headers["X-Content-Type-Options"] == "nosniff"
    from conftest import Client
    anon = Client(app)                                          # loginsiden kan vise logoet uden login
    assert anon.get("/branding/logo/1").status_code == 200
    page = anon.get("/login").get_data(as_text=True)               # loginsiden er neutral: hverken logo, farve eller klubnavn
    assert "/branding/logo/" not in page and "--navy2" not in page and "Klub" not in page
    known = app.test_client()                                    # enheden husker seneste login → klubbens udseende
    known.set_cookie("u11_lc", "1")
    assert "/branding/logo/1?v=" in known.get("/login").get_data(as_text=True)
    junk = app.test_client()
    junk.set_cookie("u11_lc", "999")
    assert "/branding/logo/" not in junk.get("/login").get_data(as_text=True)
    assert "/branding/logo/1?v=" in team.get("/").get_data(as_text=True)
    team.post("/admin/club", {"action": "remove_logo"}, page="/admin/club")
    assert team.get("/branding/logo/1").status_code == 404


@pytest.mark.parametrize("name,data,msg", [
    ("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "PNG, JPEG eller WebP"),
    ("x.png", b"<html><script>alert(1)</script></html>", "PNG, JPEG eller WebP"),          # forklædt som png
    ("big.png", png_bytes() + b"0" * (512 * 1024), "512 kB"),
])
def test_bad_logo_rejected(app, team, name, data, msg):
    r = save(team, logo=(name, data))
    assert msg in r.get_data(as_text=True)
    assert team.get("/branding/logo/1").status_code == 404


@pytest.mark.parametrize("color", ["red", "#fff", "#ffff00", "#12345g", "javascript:1"])
def test_bad_color_rejected(team, color):
    r = save(team, color=color)
    html = r.get_data(as_text=True)
    assert "Farven skal" in html or "mørkere" in html
    assert "--navy2:" + color not in team.get("/").get_data(as_text=True)


def test_trainer_cannot_edit_club(app, team):
    t = make_trainer(app, team, "tr", ["U11 piger"])
    assert t.get("/admin/club").status_code == 403
    assert t.post("/admin/club", {"action": "remove_logo"}, page="/").status_code == 403


def test_compose_uses_port_1020():
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    assert "${U11_PORT:-1020}:8000" in (root / "compose.yaml").read_text()
    assert "U11_PORT=1020" in (root / ".env.example").read_text()


def test_app_name_defaults_and_is_configurable(app, team):
    html = team.get("/").get_data(as_text=True)
    assert "Team Udvikling" in html and "U11 Udvikling" not in html
    save(team, app_name="Holdets Model")
    html = team.get("/").get_data(as_text=True)
    assert "Holdets Model" in html and "Team Udvikling" not in html
    assert "<title>" in html and "Holdets Model</title>" in html
    save(team, app_name="  ")                                           # tomt → standardnavn
    assert "Team Udvikling" in team.get("/").get_data(as_text=True)
    save(team, app_name="<b>x</b>")
    assert "<b>x</b>" not in team.get("/").get_data(as_text=True)
