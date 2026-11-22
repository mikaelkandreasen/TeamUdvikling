"""Holdets egne farver for score 1–5, forklaring nederst på siden og afgrænsning pr. hold."""
from app import charts, heatcfg
from helpers import add_player, make_team, make_trainer, player_id, score_all, switch, team_id


def _team_with_scores(app, admin):
    make_team(admin, "Farve A")
    make_team(admin, "Farve B")
    switch(admin, team_id(app, "Farve A"))
    add_player(admin, "Anna Alfa")
    score_all(admin, 1, player_id(app, "Anna Alfa"), 4)


def test_defaults_unchanged_outside_request():
    assert charts.heat(3) == "#63be7b" and charts.heat(None) == "#f2f2f2"
    assert heatcfg.text_color("#000080") == "#ffffff" and heatcfg.text_color("#ffeb84") == "#1b1b1b"


def test_custom_colors_labels_legend_and_block_mode(app, admin):
    _team_with_scores(app, admin)
    data = {f"color_{n}": c for n, c in enumerate(["#ff0000", "#ffa500", "#00a000", "#000080", "#800080"], 1)}
    data.update({f"label_{n}": f"Tekst {n}" for n in range(1, 6)}, mode="blok")
    assert admin.post("/team/farver", data, page="/team/farver").status_code == 302
    page = admin.get("/overview").get_data(as_text=True)
    assert "background:#000080;color:#ffffff" in page                       # 4,0 med egen farve og hvid tekst
    assert "Forklaring" in page and "Tekst 4" in page and "Tekst 1" in page  # forklaring nederst
    assert "blanding af nabofarverne" not in page                            # faste blokke
    # andet hold bruger stadig standardfarverne
    switch(admin, team_id(app, "Farve B"))
    add_player(admin, "Bo Beta")
    score_all(admin, 1, player_id(app, "Bo Beta"), 4)
    page_b = admin.get("/overview").get_data(as_text=True)
    assert "#000080" not in page_b and "#e0b020" in page_b and "Tekst 4" not in page_b
    switch(admin, team_id(app, "Farve A"))
    admin.post("/team/farver", {"action": "reset"}, page="/team/farver")
    assert "#e0b020" in admin.get("/overview").get_data(as_text=True)


def test_invalid_color_is_rejected_and_label_html_is_escaped(app, admin):
    _team_with_scores(app, admin)
    data = {f"color_{n}": "#123456" for n in range(1, 6)}
    data.update({"color_3": "red;background:url(x)", "label_1": "<script>x</script>", "mode": "glide"})
    admin.post("/team/farver", data, page="/team/farver")
    assert "url(x)" not in admin.get("/overview").get_data(as_text=True)
    data["color_3"] = "#123456"
    admin.post("/team/farver", data, page="/team/farver")
    page = admin.get("/overview").get_data(as_text=True)
    assert "<script>x</script>" not in page and "&lt;script&gt;" in page


def test_only_head_coach_or_admin_can_change_colors(app, admin):
    _team_with_scores(app, admin)
    tr = make_trainer(app, admin, "tove", ["Farve A"])
    assert tr.get("/team/farver").status_code in (302, 403)
    data = {f"color_{n}": "#000000" for n in range(1, 6)}
    data["mode"] = "glide"
    assert tr.post("/team/farver", data, page="/").status_code in (302, 403)
    assert "#000000" not in admin.get("/overview").get_data(as_text=True)
    assert "Ret farver" not in tr.get("/overview").get_data(as_text=True)    # trænere ser forklaringen, men ikke linket
