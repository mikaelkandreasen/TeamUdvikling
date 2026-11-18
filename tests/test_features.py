"""Backlog, evalueringsrunder/-data, 'se som træner' og trænere på flere hold."""
import re

import pytest

from helpers import add_player, make_team, make_trainer, player_id, score_all, switch, team_id
from test_import import rows


# ------------------------------------------------------------------ backlog
def test_backlog_seed_add_prioritise_reorder_delete(app, admin):
    html = admin.get("/admin/backlog").get_data(as_text=True)
    assert "Verificér Docker-build" in html                              # startliste
    admin.post("/admin/backlog", {"action": "add", "title": "Ny idé", "priority": "0"}, page="/admin/backlog")
    first = rows(app, "SELECT * FROM backlog_items ORDER BY priority, position, id LIMIT 1")[0]
    items0 = [r["title"] for r in rows(app, "SELECT title FROM backlog_items WHERE priority=0 ORDER BY position, id")]
    assert items0[-1] == "Ny idé"
    new_id = rows(app, "SELECT id FROM backlog_items WHERE title='Ny idé'")[0]["id"]
    admin.post("/admin/backlog", {"action": "up", "id": new_id}, page="/admin/backlog")
    assert [r["title"] for r in rows(app, "SELECT title FROM backlog_items WHERE priority=0 ORDER BY position, id")][-2] == "Ny idé"
    admin.post("/admin/backlog", {"action": "save", "id": new_id, "title": "Omdøbt", "description": "x", "priority": "3", "status": "Færdig"}, page="/admin/backlog")
    r = rows(app, "SELECT * FROM backlog_items WHERE id=?", new_id)[0]
    assert (r["title"], r["priority"], r["status"]) == ("Omdøbt", 3, "Færdig")
    admin.post("/admin/backlog", {"action": "delete", "id": new_id}, page="/admin/backlog")
    assert not rows(app, "SELECT 1 FROM backlog_items WHERE id=?", new_id)
    n = rows(app, "SELECT COUNT(*) c FROM backlog_items")[0]["c"]
    admin.get("/admin/backlog")                                           # ingen gen-seedning
    assert rows(app, "SELECT COUNT(*) c FROM backlog_items")[0]["c"] == n


def test_backlog_invalid_input_and_trainer_blocked(app, admin):
    admin.get("/admin/backlog")
    admin.post("/admin/backlog", {"action": "add", "title": "x", "priority": "99"}, page="/admin/backlog")
    assert rows(app, "SELECT priority FROM backlog_items WHERE title='x'")[0]["priority"] == 2
    admin.post("/admin/backlog", {"action": "save", "id": "999999", "title": "x"}, page="/admin/backlog")
    make_team(admin, "A")
    t = make_trainer(app, admin, "tr", ["A"])
    assert t.get("/admin/backlog").status_code == 403
    assert t.post("/admin/backlog", {"action": "add", "title": "hack"}, page="/").status_code == 403
    assert "<script>" not in admin.get("/admin/backlog").get_data(as_text=True)


# ------------------------------------------------------------------ evalueringsrunder og -data
def test_add_and_remove_rounds(app, admin):
    make_team(admin, "A"); add_player(admin, "Anna Alfa")
    pid = player_id(app, "Anna Alfa")
    assert admin.get("/eval/5").status_code == 404
    admin.post("/admin/evaluations", {"action": "add_round"}, page="/admin/evaluations")
    assert admin.get("/eval/5").status_code == 200
    score_all(admin, 5, pid, 4)
    assert rows(app, "SELECT COUNT(*) c FROM evaluations WHERE round=5")[0]["c"] == 24
    assert admin.get("/overview/5").status_code == 200 and admin.get(f"/profile/{pid}").status_code == 200
    admin.post("/admin/evaluations", {"action": "remove_round"}, page="/admin/evaluations")          # uden bekræftelse
    assert admin.get("/eval/5").status_code == 200
    admin.post("/admin/evaluations", {"action": "remove_round", "confirm": "ja"}, page="/admin/evaluations")
    assert admin.get("/eval/5").status_code == 404
    assert rows(app, "SELECT COUNT(*) c FROM evaluations WHERE round=5")[0]["c"] == 0


def test_round_limits_and_team_isolation(app, admin):
    make_team(admin, "A"); make_team(admin, "B")
    switch(admin, team_id(app, "A"))
    for _ in range(10):
        admin.post("/admin/evaluations", {"action": "add_round"}, page="/admin/evaluations")
    assert admin.get("/eval/8").status_code == 200 and admin.get("/eval/9").status_code == 404
    switch(admin, team_id(app, "B"))
    assert admin.get("/eval/5").status_code == 404                        # hold B er upåvirket
    for _ in range(5):
        admin.post("/admin/evaluations", {"action": "remove_round", "confirm": "ja"}, page="/admin/evaluations")
    assert admin.get("/eval/2").status_code == 200 and admin.get("/eval/3").status_code == 404   # mindst 2


def test_delete_evaluations_scoped_to_round_trainer_player_and_team(app, admin):
    make_team(admin, "A"); make_team(admin, "B")
    switch(admin, team_id(app, "A")); add_player(admin, "Anna Alfa"); add_player(admin, "Bella Beta")
    a, b = player_id(app, "Anna Alfa"), player_id(app, "Bella Beta")
    for p in (a, b):
        score_all(admin, 1, p, 3); score_all(admin, 2, p, 3)
    switch(admin, team_id(app, "B")); add_player(admin, "Clara Gamma"); c = player_id(app, "Clara Gamma")
    score_all(admin, 1, c, 3)
    uid = rows(app, "SELECT id FROM users WHERE username='admin'")[0]["id"]
    switch(admin, team_id(app, "A"))
    admin.post("/admin/evaluations", {"action": "delete_evals", "round": "1", "trainer": uid, "player": a}, page="/admin/evaluations")   # ingen bekræftelse
    assert rows(app, "SELECT COUNT(*) c FROM evaluations")[0]["c"] == 24 * 5
    admin.post("/admin/evaluations", {"action": "delete_evals", "round": "1", "trainer": uid, "player": a, "confirm": "ja"}, page="/admin/evaluations")
    assert rows(app, "SELECT COUNT(*) c FROM evaluations WHERE player_id=? AND round=1", a)[0]["c"] == 0
    admin.post("/admin/evaluations", {"action": "delete_evals", "round": "1", "trainer": uid, "player": "", "confirm": "ja"}, page="/admin/evaluations")
    assert rows(app, "SELECT COUNT(*) c FROM evaluations WHERE round=1 AND player_id=?", b)[0]["c"] == 0
    assert rows(app, "SELECT COUNT(*) c FROM evaluations WHERE round=2 AND player_id=?", b)[0]["c"] == 24     # anden runde urørt
    assert rows(app, "SELECT COUNT(*) c FROM evaluations WHERE player_id=?", c)[0]["c"] == 24                 # andet hold urørt
    log = " ".join(r["detail"] or "" for r in rows(app, "SELECT detail FROM audit_log"))
    assert "Anna" not in log and "Bella" not in log


def test_trainer_cannot_touch_round_admin(app, admin):
    make_team(admin, "A")
    t = make_trainer(app, admin, "tr", ["A"])
    assert t.get("/admin/evaluations").status_code == 403
    assert t.post("/admin/evaluations", {"action": "add_round"}, page="/").status_code == 403


# ------------------------------------------------------------------ se som træner
def test_view_as_trainer_is_readonly_and_scoped(app, admin):
    make_team(admin, "A"); make_team(admin, "B")
    switch(admin, team_id(app, "A")); add_player(admin, "Anna Alfa")
    t = make_trainer(app, admin, "tr", ["A"])
    uid = rows(app, "SELECT id FROM users WHERE username='tr'")[0]["id"]
    r = admin.post(f"/admin/users/{uid}/view-as", {}, page="/admin/users")
    assert r.status_code == 302
    page = admin.get("/", follow_redirects=True).get_data(as_text=True)
    assert "Du ser siden som" in page and "Tr" in page
    assert admin.get("/admin/").status_code == 403                         # ser præcis det en træner ser
    assert admin.get("/players/").status_code == 200
    assert switch(admin, team_id(app, "B")).status_code == 403             # kun trænerens hold
    assert admin.post("/players/new", {"name": "Hack", "birth_date": "2016-01-01"}, page="/players/new").status_code == 403
    assert admin.post("/eval/1/1", {"c0": "5"}, page="/players/").status_code in (403, 404)
    assert not rows(app, "SELECT 1 FROM players WHERE name='Hack'")
    assert rows(app, "SELECT COUNT(*) c FROM evaluations")[0]["c"] == 0
    admin.post("/view-as/stop", {}, page="/players/")
    assert admin.get("/admin/").status_code == 200 and "Du ser siden som" not in admin.get("/").get_data(as_text=True)
    log = " ".join(f"{r['user']} {r['action']}" for r in rows(app, "SELECT user, action FROM audit_log"))
    assert "admin se_som_traener" in log


def test_view_as_cannot_target_admin_or_be_started_by_trainer(app, admin):
    make_team(admin, "A")
    t = make_trainer(app, admin, "tr", ["A"])
    admin_id = rows(app, "SELECT id FROM users WHERE username='admin'")[0]["id"]
    assert admin.post(f"/admin/users/{admin_id}/view-as", {}, page="/admin/users").status_code == 404
    tid = rows(app, "SELECT id FROM users WHERE username='tr'")[0]["id"]
    assert t.post(f"/admin/users/{tid}/view-as", {}, page="/").status_code == 403
    with t.c.session_transaction() as s:                                    # forfalsket session-felt virker ikke for trænere
        s["view_as"] = admin_id
    assert "Du ser siden som" not in t.get("/").get_data(as_text=True)


# ------------------------------------------------------------------ én træner, flere hold
def test_trainer_on_multiple_teams_switches_and_stays_isolated(app, admin):
    for n in ("U10", "U11", "U12"):
        make_team(admin, n)
    for n in ("U10", "U11", "U12"):
        switch(admin, team_id(app, n)); add_player(admin, f"Spiller {n}")
    t = make_trainer(app, admin, "tr", ["U10", "U11"])
    home = t.get("/").get_data(as_text=True)
    assert "U10" in home and "U11" in home and "U12" not in home
    assert switch(t, team_id(app, "U11")).status_code == 302
    assert "Spiller U11" in t.get("/players/").get_data(as_text=True)
    assert switch(t, team_id(app, "U10")).status_code == 302
    page = t.get("/players/").get_data(as_text=True)
    assert "Spiller U10" in page and "Spiller U11" not in page
    assert switch(t, team_id(app, "U12")).status_code == 403
    assert t.get(f"/profile/{player_id(app, 'Spiller U12')}").status_code == 404
    # tildel flere hold efterfølgende
    uid = rows(app, "SELECT id FROM users WHERE username='tr'")[0]["id"]
    admin.c.post(f"/admin/users/{uid}/teams", data={"teams": [str(team_id(app, "U12"))], "csrf_token": admin.token("/admin/users")})
    assert switch(t, team_id(app, "U12")).status_code == 302
