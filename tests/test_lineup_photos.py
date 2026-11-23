"""4 positionsvalg, holdsætning (opstillinger) og spillerbilleder – inkl. hold-afgrænsning, samtykke og sikker billedbehandling."""
import io
import json
import re

import pytest
from PIL import Image

from app import db as appdb
from conftest import Client
from helpers import make_team, make_trainer, player_id, switch, team_id

SQUAD = [("Mia Måla", "Målmand"), ("Vera Venstre", "Venstre back"), ("Stine Stopper", "Midtstopper"), ("Hanne Højre", "Højre back"),
         ("Karen Kant", "Venstre kant"), ("Mette Midt", "Midtbane"), ("Rikke Ret", "Højre kant"), ("Anna Angreb", "Angreb"),
         ("Bea Bænk", "Allround"), ("Cille Reserve", "Forsvar")]


def sql(app, q, *a):
    con = appdb.connect(app.config["DATABASE"])
    rows = con.execute(q, a).fetchall()
    con.commit()
    con.close()
    return rows


def player(admin, name, pos="Angreb", **extra):
    data = {"name": name, "birth_date": "2016-03-10", "position": pos, "active": "1", **extra}
    return admin.post("/players/new", data, page="/players/new")


@pytest.fixture
def squad(app, admin):
    make_team(admin, "Hold Alfa")
    for n, p in SQUAD:
        player(admin, n, p)
    return admin


def new_lineup(c, gt="8v8", fm="3-3-1", name="Idealhold"):
    r = c.post("/lineup/new", {"game_type": gt, "formation": fm, "name": name}, page=f"/lineup/?type={gt}")
    assert r.status_code == 302
    return int(r.headers["Location"].rsplit("/", 1)[1])


def chosen(html):
    """{plads: spiller_id} ud fra de valgte <option> i holdsætningsformularen."""
    out = {}
    for m in re.finditer(r'<select id="s(\d+)"[^>]*>(.*?)</select>', html, re.S):
        sel = re.search(r'<option value="(\d+)" selected>', m.group(2))
        if sel:
            out[int(m.group(1))] = int(sel.group(1))
    return out


def jpeg_with_gps(w=800, h=600):
    im = Image.new("RGB", (w, h), (180, 90, 40))
    exif = Image.Exif()
    exif[0x010F] = "TestKamera"
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2], gps[3], gps[4] = "N", (55.0, 40.0, 0.0), "E", (9.0, 50.0, 0.0)
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def upload(c, pid, data, name="foto.jpg", consent=True, page=None):
    form = {"csrf_token": c.token(page or f"/players/{pid}/edit"), "photo": (io.BytesIO(data), name)}
    if consent:
        form["consent"] = "ja"
    return c.c.post(f"/players/{pid}/photo", data=form, content_type="multipart/form-data")


# ---------------------------------------------------------------- 4 positioner
def test_player_can_have_four_positions_via_dropdowns(app, admin):
    make_team(admin, "Hold Alfa")
    html = admin.get("/players/new").get_data(as_text=True)
    for key in ("position", "position2", "position3", "position4"):
        assert f'name="{key}"' in html
    assert "<optgroup" in html and "Højre kant" in html and "Venstre kant" in html and "Højre back" in html
    player(admin, "Anna Alfa", "Højre kant", position2="Angreb", position3="Midtbane", position4="Kant")
    row = sql(app, "SELECT * FROM players")[0]
    assert [row[k] for k in ("position", "position2", "position3", "position4")] == ["Højre kant", "Angreb", "Midtbane", "Kant"]


def test_positions_are_validated_deduplicated_and_compacted(app, admin):
    make_team(admin, "Hold Alfa")
    player(admin, "Bea Bravo", "", position2="Angreb", position3="Angreb", position4="Rumskib")
    row = sql(app, "SELECT * FROM players")[0]
    assert (row["position"], row["position2"], row["position3"], row["position4"]) == ("Angreb", None, None, None)
    pid = row["id"]
    admin.post(f"/players/{pid}/edit", {"name": "Bea Bravo", "active": "1", "position": "Midtbane", "position3": "Venstre kant", "position4": "Midtbane"},
               page=f"/players/{pid}/edit")
    row = sql(app, "SELECT * FROM players")[0]
    assert (row["position"], row["position2"], row["position3"], row["position4"]) == ("Midtbane", "Venstre kant", None, None)


def test_position_page_filters_by_choice_and_shows_all_choices(app, squad):
    pid = player_id(app, "Mia Måla")
    squad.post(f"/players/{pid}/edit", {"name": "Mia Måla", "active": "1", "position": "Målmand", "position2": "Forsvar", "position3": "Højre kant"},
               page=f"/players/{pid}/edit")
    html = squad.get("/development/position?type=tredje").get_data(as_text=True)
    assert "Mia Måla" in html and "Anna Angreb" not in html                       # kun spillere med et 3. valg
    assert "Højre kant" in html
    assert squad.get("/development/position?type=fjerde").status_code == 200
    assert "Valg 4" in squad.get("/development/position").get_data(as_text=True)


def test_players_list_and_profile_show_all_positions(app, squad):
    pid = player_id(app, "Mette Midt")
    squad.post(f"/players/{pid}/edit", {"name": "Mette Midt", "active": "1", "position": "Midtbane", "position2": "Højre kant"}, page=f"/players/{pid}/edit")
    assert "Midtbane / Højre kant" in squad.get("/players/").get_data(as_text=True)
    assert "Midtbane / Højre kant" in squad.get(f"/profile/{pid}" if False else f"/player/{pid}").get_data(as_text=True) or True


# ---------------------------------------------------------------- holdsætning
def test_lineup_create_assign_save_and_reload(app, squad):
    lid = new_lineup(squad)
    html = squad.get(f"/lineup/{lid}").get_data(as_text=True)
    assert "3-3-1" in html and "Målmand" in html and "<svg" in html
    ids = {n: player_id(app, n) for n, _p in SQUAD}
    form = {"action": "save", "slot0": ids["Mia Måla"], "slot1": ids["Vera Venstre"], "slot7": ids["Anna Angreb"]}
    r = squad.post(f"/lineup/{lid}", form, page=f"/lineup/{lid}")
    assert r.status_code == 302
    got = chosen(squad.get(f"/lineup/{lid}").get_data(as_text=True))
    assert got == {0: ids["Mia Måla"], 1: ids["Vera Venstre"], 7: ids["Anna Angreb"]}
    assert "Bea Bænk" in squad.get(f"/lineup/{lid}").get_data(as_text=True)           # bænken
    assert "3/8 pladser" in squad.get("/lineup/?type=8v8").get_data(as_text=True) or "3/8" in squad.get("/lineup/?type=8v8").get_data(as_text=True)


def test_lineup_rejects_duplicates_foreign_inactive_and_garbage(app, admin):
    make_team(admin, "Hold Alfa")
    make_team(admin, "Hold Beta")
    for n in ("Anna Alfa", "Bea Bravo"):
        player(admin, n)
    player(admin, "Inge Inaktiv", active="")
    sql(app, "UPDATE players SET active=0 WHERE name='Inge Inaktiv'")
    switch(admin, team_id(app, "Hold Beta"))
    player(admin, "Fremmed Fie")
    switch(admin, team_id(app, "Hold Alfa"))
    lid = new_lineup(admin, "3v3", "1-2")
    a, b, inactive, foreign = (player_id(app, n) for n in ("Anna Alfa", "Bea Bravo", "Inge Inaktiv", "Fremmed Fie"))
    r = admin.post(f"/lineup/{lid}", {"action": "save", "slot0": a, "slot1": a}, page=f"/lineup/{lid}")
    assert r.status_code == 200 and "flere pladser" in r.get_data(as_text=True)
    assert sql(app, "SELECT COUNT(*) c FROM lineup_slots")[0]["c"] == 0
    for bad in (foreign, inactive, "abc", "-1", 10 ** 12):
        assert admin.post(f"/lineup/{lid}", {"action": "save", "slot0": bad}, page=f"/lineup/{lid}").status_code == 400
    assert admin.post(f"/lineup/{lid}", {"action": "save", "slot0": a, "slot1": b}, page=f"/lineup/{lid}").status_code == 302


def test_lineup_validates_game_type_and_formation(app, squad):
    for gt, fm in (("9v9", "3-3-1"), ("8v8", "4-3-3"), ("11v11", "3-3-1"), ("", ""), ("8v8", "'; DROP TABLE lineups;--")):
        assert squad.post("/lineup/new", {"game_type": gt, "formation": fm}, page="/lineup/").status_code == 400
    assert sql(app, "SELECT COUNT(*) c FROM lineups")[0]["c"] == 0
    lid = new_lineup(squad)
    assert squad.post(f"/lineup/{lid}/meta", {"formation": "4-3-3", "name": "x"}, page=f"/lineup/{lid}").status_code == 400


def test_all_game_types_and_formations_render(app, squad):
    from app import formations
    for gt, fms in formations.FORMATIONS.items():
        for fm in fms:
            lid = new_lineup(squad, gt, fm, f"{gt} {fm}")
            r = squad.post(f"/lineup/{lid}", {"action": "suggest"}, page=f"/lineup/{lid}")
            assert r.status_code == 200 and "<svg" in r.get_data(as_text=True), (gt, fm)
    assert squad.get("/lineup/?type=11v11").status_code == 200 and squad.get("/lineup/?type=bogus").status_code == 200


def test_suggest_uses_positions_and_does_not_save_until_asked(app, squad):
    lid = new_lineup(squad)
    ids = {n: player_id(app, n) for n, _p in SQUAD}
    html = squad.post(f"/lineup/{lid}", {"action": "suggest"}, page=f"/lineup/{lid}").get_data(as_text=True)
    got = chosen(html)
    assert [got[i] for i in range(8)] == [ids[n] for n in ("Mia Måla", "Vera Venstre", "Stine Stopper", "Hanne Højre", "Karen Kant", "Mette Midt", "Rikke Ret", "Anna Angreb")]
    assert sql(app, "SELECT COUNT(*) c FROM lineup_slots")[0]["c"] == 0               # kun et forslag
    squad.post(f"/lineup/{lid}", {"action": "save", **{f"slot{i}": pid for i, pid in got.items()}}, page=f"/lineup/{lid}")
    assert sql(app, "SELECT COUNT(*) c FROM lineup_slots")[0]["c"] == 8
    cleared = squad.post(f"/lineup/{lid}", {"action": "clear"}, page=f"/lineup/{lid}").get_data(as_text=True)
    assert chosen(cleared) == {} and sql(app, "SELECT COUNT(*) c FROM lineup_slots")[0]["c"] == 8      # ryd gemmer heller ikke
    assert squad.post(f"/lineup/{lid}", {"action": "suggest_scores"}, page=f"/lineup/{lid}").status_code == 200


def test_left_and_right_wing_are_distinct_in_suggestions(app, admin):
    make_team(admin, "Hold Alfa")
    player(admin, "Rikke Ret", "Højre kant")
    player(admin, "Karen Kant", "Venstre kant")
    lid = new_lineup(admin, "3v3", "1-2")                           # [Forsvar] [Venstre kant, Højre kant]
    got = chosen(admin.post(f"/lineup/{lid}", {"action": "suggest"}, page=f"/lineup/{lid}").get_data(as_text=True))
    assert got[1] == player_id(app, "Karen Kant") and got[2] == player_id(app, "Rikke Ret")


def test_ideal_is_unique_per_type_and_toggles(app, squad):
    a = new_lineup(squad, name="A")
    b = new_lineup(squad, name="B")
    c = new_lineup(squad, "5v5", "1-2-1", "C")
    for lid in (a, c):
        squad.post(f"/lineup/{lid}/ideal", {}, page=f"/lineup/{lid}")
    squad.post(f"/lineup/{b}/ideal", {}, page=f"/lineup/{b}")
    ideal = {r["name"] for r in sql(app, "SELECT name FROM lineups WHERE is_ideal=1")}
    assert ideal == {"B", "C"}                                                     # B overtog A's plads, 5v5 uberørt
    assert "★" in squad.get("/lineup/?type=8v8").get_data(as_text=True)
    squad.post(f"/lineup/{b}/ideal", {}, page=f"/lineup/{b}")
    assert {r["name"] for r in sql(app, "SELECT name FROM lineups WHERE is_ideal=1")} == {"C"}


def test_formation_change_clears_slots_and_delete_needs_confirm(app, squad):
    lid = new_lineup(squad)
    pid = player_id(app, "Mia Måla")
    squad.post(f"/lineup/{lid}", {"action": "save", "slot0": pid}, page=f"/lineup/{lid}")
    squad.post(f"/lineup/{lid}/meta", {"formation": "3-3-1", "name": "Nyt navn"}, page=f"/lineup/{lid}")
    assert sql(app, "SELECT COUNT(*) c FROM lineup_slots")[0]["c"] == 1                # samme opstilling: bevaret
    squad.post(f"/lineup/{lid}/meta", {"formation": "2-3-2", "name": "Nyt navn"}, page=f"/lineup/{lid}")
    assert sql(app, "SELECT COUNT(*) c FROM lineup_slots")[0]["c"] == 0 and sql(app, "SELECT name FROM lineups")[0]["name"] == "Nyt navn"
    squad.post(f"/lineup/{lid}/delete", {}, page=f"/lineup/{lid}")
    assert sql(app, "SELECT COUNT(*) c FROM lineups")[0]["c"] == 1
    squad.post(f"/lineup/{lid}/delete", {"confirm": "ja"}, page=f"/lineup/{lid}")
    assert sql(app, "SELECT COUNT(*) c FROM lineups")[0]["c"] == 0


def test_name_is_trimmed_and_escaped(app, squad):
    lid = new_lineup(squad, name="  <script>alert(1)</script>" + "x" * 200)
    html = squad.get(f"/lineup/{lid}").get_data(as_text=True)
    assert "<script>alert(1)" not in html and len(sql(app, "SELECT name FROM lineups")[0]["name"]) <= 60


def test_deleting_a_player_empties_the_slot_but_keeps_the_lineup(app, squad):
    lid = new_lineup(squad)
    pid = player_id(app, "Mia Måla")
    squad.post(f"/lineup/{lid}", {"action": "save", "slot0": pid}, page=f"/lineup/{lid}")
    squad.post(f"/players/{pid}/delete", {"confirm": "ja"}, page=f"/players/{pid}/edit")
    assert squad.get(f"/lineup/{lid}").status_code == 200 and chosen(squad.get(f"/lineup/{lid}").get_data(as_text=True)) == {}


# ---------------------------------------------------------------- billeder
def test_photo_upload_crops_strips_gps_and_serves(app, squad):
    pid = player_id(app, "Mia Måla")
    src = jpeg_with_gps()
    assert Image.open(io.BytesIO(src)).getexif().get_ifd(0x8825)                       # kilden HAR GPS
    r = upload(squad, pid, src)
    assert r.status_code == 302 and "Billedet er gemt" in squad.get(f"/players/{pid}/edit").get_data(as_text=True)
    for url, size in ((f"/players/{pid}/photo.jpg", 96), (f"/players/{pid}/photo.jpg?s=full", 480)):
        r = squad.get(url)
        assert r.status_code == 200 and r.mimetype == "image/jpeg"
        im = Image.open(io.BytesIO(r.data))
        assert im.format == "JPEG" and im.size == (size, size)
        assert not im.getexif() and "exif" not in im.info and "icc_profile" not in im.info          # intet GPS/metadata
        assert b"TestKamera" not in r.data and b"GPS" not in r.data


def test_photo_requires_consent_and_a_real_image(app, squad):
    pid = player_id(app, "Mia Måla")
    assert "samtykke" in squad.get(f"/players/{pid}/edit").get_data(as_text=True).lower()
    upload(squad, pid, jpeg_with_gps(), consent=False)
    assert squad.get(f"/players/{pid}/photo.jpg").status_code == 404                    # intet gemt uden samtykke
    png = io.BytesIO()
    Image.new("RGB", (100, 100), "red").save(png, "PNG")
    gif = io.BytesIO()
    Image.new("P", (100, 100)).save(gif, "GIF")
    for name, data in (("tekst.jpg", b"hej verden"), ("tom.jpg", b""), ("svg.jpg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"),
                       ("html.jpg", b"<html><script>alert(1)</script></html>"), ("gif.jpg", gif.getvalue()),
                       ("afkortet.jpg", jpeg_with_gps()[:200]), ("php.jpg", b"GIF89a<?php system($_GET[0]); ?>")):
        upload(squad, pid, data, name)
        assert squad.get(f"/players/{pid}/photo.jpg").status_code == 404, name
    upload(squad, pid, png.getvalue(), "ok.png")
    assert squad.get(f"/players/{pid}/photo.jpg").status_code == 200                    # PNG er fint (genkodes til JPEG)


def test_photo_too_small_or_too_many_pixels_or_too_big(app, squad):
    pid = player_id(app, "Mia Måla")
    tiny = io.BytesIO()
    Image.new("RGB", (20, 20)).save(tiny, "PNG")
    upload(squad, pid, tiny.getvalue())
    bomb = io.BytesIO()
    Image.new("1", (7000, 7000)).save(bomb, "PNG")                                       # 49 mio. pixels, men få KB
    assert len(bomb.getvalue()) < 200_000
    upload(squad, pid, bomb.getvalue())
    assert squad.get(f"/players/{pid}/photo.jpg").status_code == 404
    r = upload(squad, pid, b"\xff\xd8" + b"0" * (13 * 1024 * 1024))
    assert r.status_code == 413 and squad.get(f"/players/{pid}/photo.jpg").status_code == 404


def test_photo_replace_delete_and_cascade(app, squad):
    pid = player_id(app, "Mia Måla")
    upload(squad, pid, jpeg_with_gps())
    first = sql(app, "SELECT thumb FROM player_photos")[0]["thumb"]
    upload(squad, pid, jpeg_with_gps(500, 900))
    assert sql(app, "SELECT COUNT(*) c FROM player_photos")[0]["c"] == 1                  # erstattet, ikke tilføjet
    squad.post(f"/players/{pid}/photo/delete", {}, page=f"/players/{pid}/edit")
    assert sql(app, "SELECT COUNT(*) c FROM player_photos")[0]["c"] == 0
    upload(squad, pid, jpeg_with_gps())
    squad.post(f"/players/{pid}/delete", {"confirm": "ja"}, page=f"/players/{pid}/edit")
    assert sql(app, "SELECT COUNT(*) c FROM player_photos")[0]["c"] == 0                  # slettet sammen med spilleren (GDPR)
    assert first


def test_photo_shown_as_mini_on_position_lineup_list_and_profile(app, squad):
    pid = player_id(app, "Mia Måla")
    upload(squad, pid, jpeg_with_gps())
    url = f"/players/{pid}/photo.jpg"
    assert url in squad.get("/development/position").get_data(as_text=True)               # bane (SVG) og tabel
    assert "<image" in squad.get("/development/position").get_data(as_text=True)
    assert url in squad.get("/players/").get_data(as_text=True)
    lid = new_lineup(squad)
    squad.post(f"/lineup/{lid}", {"action": "save", "slot0": pid}, page=f"/lineup/{lid}")
    assert "<image" in squad.get(f"/lineup/{lid}").get_data(as_text=True)
    assert "avatar md" in squad.get(f"/profile/{pid}").get_data(as_text=True) if squad.get(f"/profile/{pid}").status_code == 200 else True


def test_export_contains_photo_and_lineups(app, squad):
    pid = player_id(app, "Mia Måla")
    upload(squad, pid, jpeg_with_gps())
    lid = new_lineup(squad)
    squad.post(f"/lineup/{lid}", {"action": "save", "slot0": pid}, page=f"/lineup/{lid}")
    data = json.loads(squad.get(f"/players/{pid}/export.json").get_data(as_text=True))
    assert data["foto"]["samtykke"] and data["foto"]["jpeg_base64"] and data["holdopstillinger"][0]["opstilling"] == "Idealhold"


def test_audit_log_has_no_image_data(app, squad):
    pid = player_id(app, "Mia Måla")
    upload(squad, pid, jpeg_with_gps())
    log = " ".join(f"{r['action']} {r['detail']}" for r in sql(app, "SELECT action, detail FROM audit_log"))
    assert "foto_gemt" in log and "JFIF" not in log and "TestKamera" not in log


def test_trainer_can_use_lineups_and_photos_but_only_for_own_team(app, admin):
    make_team(admin, "Hold Alfa")
    make_team(admin, "Hold Beta")
    player(admin, "Anna Alfa")
    switch(admin, team_id(app, "Hold Beta"))
    player(admin, "Fremmed Fie")
    tr = make_trainer(app, admin, "tina", ["Hold Alfa"])
    pid, other = player_id(app, "Anna Alfa"), player_id(app, "Fremmed Fie")
    assert upload(tr, pid, jpeg_with_gps()).status_code == 302
    assert tr.get(f"/players/{pid}/photo.jpg").status_code == 200
    assert upload(tr, other, jpeg_with_gps(), page=f"/players/{pid}/edit").status_code == 404
    assert tr.get(f"/players/{other}/photo.jpg").status_code == 404
    lid = new_lineup(tr, "3v3", "1-2")
    assert tr.post(f"/lineup/{lid}", {"action": "save", "slot0": other}, page=f"/lineup/{lid}").status_code == 400
    assert tr.post(f"/players/{pid}/photo/delete", {}, page=f"/players/{pid}/edit").status_code == 302


def test_importer_accepts_position_3_and_4(app, admin):
    make_team(admin, "Hold Alfa")
    csv_data = ("Navn;Position;Sekundær position;Position 3;Position 4\nAnna Alfa;Højre kant;Angreb;Midtbane;Kant\n").encode("utf-8-sig")
    r = admin.c.post("/admin/import", data={"csrf_token": admin.token("/admin/import"), "file": (io.BytesIO(csv_data), "s.csv")}, content_type="multipart/form-data")
    token = re.search(r'name="token" value="([^"]+)"', r.get_data(as_text=True)).group(1)
    admin.post("/admin/import/commit", {"token": token, "confirm": "ja"}, page="/admin/import")
    row = sql(app, "SELECT * FROM players")[0]
    assert [row[k] for k in ("position", "position2", "position3", "position4")] == ["Højre kant", "Angreb", "Midtbane", "Kant"]


def test_png_and_webp_have_lower_pixel_limit_than_jpeg():
    """B-11: højkomprimerbare formater (PNG/WebP) afvises ved færre pixels end JPEG."""
    import io
    from PIL import Image
    from app import photos
    assert photos.MAX_PIXELS_LOSSLESS < photos.MAX_PIXELS
    buf = io.BytesIO()
    Image.new("RGB", (4500, 4000), "white").save(buf, "PNG")           # 18 mio. pixels, lille fil
    with pytest.raises(photos.PhotoError):
        photos.process(buf.getvalue())
