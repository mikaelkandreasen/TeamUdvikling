"""Aktive brugere, brugsstatistik (15 min) og evalueringens åbne spillertyper."""
import re
import time

import pytest

from app import activity
from app import db as appdb
from conftest import Client
from helpers import add_player, make_team, make_trainer, player_id, switch, team_id


def sql(app, q, *a):
    con = appdb.connect(app.config["DATABASE"])
    rows = con.execute(q, a).fetchall()
    con.commit()
    con.close()
    return rows


@pytest.fixture
def two(app, admin):
    make_team(admin, "U11 Alfa")
    make_team(admin, "U12 Beta")
    return admin


def test_activity_recorded_for_logged_in_user_only(app, admin):
    make_team(admin, "U11 Alfa")
    assert sql(app, "SELECT COUNT(*) c FROM activity")[0]["c"] >= 1
    n = sql(app, "SELECT COUNT(*) c FROM activity")[0]["c"]
    anon = Client(app)
    anon.get("/login")
    anon.get("/healthz")
    admin.get("/static/style.css")
    assert sql(app, "SELECT COUNT(*) c FROM activity")[0]["c"] == n
    assert sql(app, "SELECT COUNT(*) c FROM presence")[0]["c"] == 1                   # kun admin
    assert admin.get("/nonexistent-page").status_code == 404                           # fejl tæller ikke


def test_only_one_row_per_user_and_quarter(app, admin):
    make_team(admin, "U11 Alfa")
    for _ in range(5):
        admin.get("/players/")
    rows = sql(app, "SELECT slot, COUNT(*) c FROM activity GROUP BY user_id, slot")
    assert all(r["c"] == 1 for r in rows)


def badge(html):
    m = re.search(r'class="onl"[^>]*>\(([^)]*)\)</a>', html)
    return m.group(1) if m else None


def test_header_badge_counts_self_and_is_scoped_to_team(app, two):
    admin = two
    t = make_trainer(app, admin, "tina", ["U11 Alfa"], email=None)
    other = make_trainer(app, admin, "ole", ["U12 Beta"])
    sql(app, "UPDATE users SET display_name='Tina Træner' WHERE username='tina'")
    sql(app, "UPDATE users SET display_name='Ole Anden' WHERE username='ole'")
    other.get("/?desktop=1")
    html = t.get("/?desktop=1").get_data(as_text=True)
    assert badge(html) == "2 aktive"                                         # Tina + administratoren (på U11 Alfa); ikke Ole på U12 Beta
    assert "<h2>Aktive nu</h2>" not in html                                  # ikke længere et kort på forsiden
    ah = admin.get("/?desktop=1").get_data(as_text=True)
    assert badge(ah) == "2/3 aktive"                                         # administrator: eget hold / i alt (admin, Tina, Ole)


def test_activity_page_shows_only_own_team_to_trainers(app, two):
    admin = two
    t = make_trainer(app, admin, "tina", ["U11 Alfa"], email=None)
    other = make_trainer(app, admin, "ole", ["U12 Beta"])
    sql(app, "UPDATE users SET display_name='Tina Træner' WHERE username='tina'")
    sql(app, "UPDATE users SET display_name='Ole Anden' WHERE username='ole'")
    other.get("/?desktop=1")
    html = t.get("/aktivitet").get_data(as_text=True)
    assert "Tina Træner" in html and "Ole Anden" not in html and "Alle hold" not in html
    ah = admin.get("/aktivitet").get_data(as_text=True)
    assert "Alle hold" in ah and "Ole Anden" in ah and "U12 Beta" in ah
    assert Client(app).get("/aktivitet").status_code == 302                  # kræver login


def test_online_window_and_summary(app, two):
    con = appdb.connect(app.config["DATABASE"])
    uid = con.execute("SELECT id FROM users LIMIT 1").fetchone()["id"]
    tid = team_id(app, "U11 Alfa")
    now = 1_800_000_000
    activity.record(con, uid, tid, now)
    assert len(activity.online(con, tid, now=now + 200)) == 1
    assert len(activity.online(con, tid, now=now + 400)) == 0                              # over 5 min
    assert len(activity.online(con, team_id(app, "U12 Beta"), now=now + 10)) == 0
    assert len(activity.online(con, everyone=True, now=now + 10)) == 1
    con.close()


def test_usage_buckets_in_local_time(app, two):
    con = appdb.connect(app.config["DATABASE"])
    uid = con.execute("SELECT id FROM users LIMIT 1").fetchone()["id"]
    con.execute("DELETE FROM activity")
    # 2026-11-17 (tirsdag) 17:30 lokal tid (CET = UTC+1) = 16:30 UTC
    import calendar
    ts = calendar.timegm((2026, 11, 17, 16, 30, 0))
    activity.record(con, uid, None, ts)
    activity.record(con, uid, None, ts + 899)                                              # samme kvarter
    activity.record(con, uid, None, ts + 900)                                              # næste kvarter
    with app.app_context():
        u = activity.usage(con, 30, now=ts + 3600)
    assert u["total"] == 2 and u["by_day"][17 * 4 + 2] == 1 and u["by_day"][17 * 4 + 3] == 1
    assert u["grid"][1][17 * 4 + 2] == 1                                                   # tirsdag
    assert {(d, k) for _v, d, k in u["top"]} == {(1, 17 * 4 + 2), (1, 17 * 4 + 3)}
    assert activity.label(70) == "17:30" and activity.label(0) == "00:00"
    con.close()


def test_usage_page_admin_only_and_renders(app, two):
    admin = two
    add = make_trainer(app, admin, "tina", ["U11 Alfa"])
    add.get("/?hold=1")
    for path in ("/admin/usage", "/admin/usage?days=7&team=1", "/admin/usage?days=abc&team=zzz", "/admin/usage?team=999"):
        r = admin.get(path)
        assert r.status_code == 200, path
    html = admin.get("/admin/usage").get_data(as_text=True)
    assert "<svg" in html and "Travleste tidspunkter" in html and "Tina" in html
    assert add.get("/admin/usage").status_code == 403
    assert "Brug" in admin.get("/admin/").get_data(as_text=True)


def test_nothing_sensitive_is_stored(app, two):
    two.get("/players/")
    cols = {r["name"] for t in ("activity", "presence") for r in sql(app, f"PRAGMA table_info({t})")}
    assert cols == {"user_id", "slot", "team_id", "last_seen"}                             # ingen IP, sti eller indhold


def test_old_activity_is_purged(app, two):
    con = appdb.connect(app.config["DATABASE"])
    uid = con.execute("SELECT id FROM users LIMIT 1").fetchone()["id"]
    old = (int(time.time()) - 200 * 86400) // 900
    con.execute("INSERT OR IGNORE INTO activity(user_id, slot, team_id) VALUES(?,?,NULL)", (uid, old))
    appdb.purge_old(con)
    assert con.execute("SELECT COUNT(*) FROM activity WHERE slot=?", (old,)).fetchone()[0] == 0
    con.close()


# ---------------------------------------------------------------- evaluering: åbne spillertyper
def eval_page(c, pid, query=""):
    return c.get(f"/eval/1/{pid}{query}").get_data(as_text=True)


def open_set(html):
    return {int(m.group(1)) for m in re.finditer(r'<details class="role" data-role="(\d)"\s+open', html)}


def test_eval_roles_open_state_is_kept_for_next_player(app, admin):
    make_team(admin, "U11 Alfa")
    for n in ("Anna Alfa", "Bea Bravo"):
        add_player(admin, n)
    a, b = player_id(app, "Anna Alfa"), player_id(app, "Bea Bravo")
    assert open_set(eval_page(admin, a)) == {0}                                            # standard: første
    r = admin.post(f"/eval/1/{a}", {"go": "next", "open": "2"}, page=f"/eval/1/{a}")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/eval/1/{b}?open=2")
    assert open_set(eval_page(admin, b, "?open=2")) == {2}                                 # kun presspiller åben
    r = admin.post(f"/eval/1/{b}", {"go": "next", "open": "1,3"}, page=f"/eval/1/{b}")     # sidste spiller → listen
    assert r.status_code == 302 and "/eval/1" in r.headers["Location"]
    assert open_set(eval_page(admin, a, "?open=")) == set()                                # alle lukket respekteres
    assert open_set(eval_page(admin, a, "?open=0,3")) == {0, 3}
    assert open_set(eval_page(admin, a, "?open=9,x,-1,1,1")) == {1}                        # ugyldigt ignoreres
    r = admin.post(f"/eval/1/{a}", {"go": "next", "open": "<script>"}, page=f"/eval/1/{a}")
    assert "script" not in r.headers["Location"].lower()


def test_eval_without_js_still_defaults_to_first_role(app, admin):
    make_team(admin, "U11 Alfa")
    for n in ("Anna Alfa", "Bea Bravo"):
        add_player(admin, n)
    a, b = player_id(app, "Anna Alfa"), player_id(app, "Bea Bravo")
    r = admin.post(f"/eval/1/{a}", {"go": "next"}, page=f"/eval/1/{a}")
    assert r.headers["Location"].endswith(f"/eval/1/{b}")
    assert open_set(eval_page(admin, b)) == {0}
