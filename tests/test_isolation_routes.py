"""B-041: automatisk isolationstest. Hver rute med et id i URL'en prøves som træner fra et ANDET hold (samme klub) og fra en ANDEN klub.
Alle skal afvises (403/404). Tilføjes en ny rute med id uden at stå her, fejler testen – så glemmes afgrænsningen aldrig stiltiende."""
import pytest

from helpers import add_player, player_id
from test_clubs_invites import make_team_in, make_user, mailapp, sql, world  # noqa: F401

# endpoint -> hvilke ressource-id'er fra holdet "Hold Alfa" ruten får (nøgle = URL-parameter)
RES = {
    "conv.add": dict(pid="pid"), "conv.delete": dict(pid="pid", cid="conv"), "conv.index": dict(pid="pid"),
    "devdata.attendance_delete": dict(eid="event"), "devdata.attendance_edit": dict(eid="event"), "devdata.plan": dict(pid="pid"),
    "evaluation.eval_form": dict(rnd=1, pid="pid"), "evaluation.profile": dict(pid="pid"),
    "inbox.delete": dict(mid="msg"), "inbox.reply": dict(mid="msg"),
    "lineup.delete": dict(lid="lineup"), "lineup.edit": dict(lid="lineup"), "lineup.ideal": dict(lid="lineup"), "lineup.meta": dict(lid="lineup"),
    "matches.delete": dict(mid="match"), "matches.edit": dict(mid="match"), "matches.meta": dict(mid="match"), "matches.ical_update": dict(mid="match"),
    "motivation.link_revoke": dict(lid="plink"), "motivation.report": dict(pid="pid"), "motivation.tablet": dict(pid="pid"),
    "players.delete": dict(pid="pid"), "players.edit": dict(pid="pid"), "players.export_json": dict(pid="pid"), "players.move": dict(pid="pid"),
    "players.photo_delete": dict(pid="pid"), "players.photo_upload": dict(pid="pid"), "players.photo_view": dict(pid="pid"),
    "reports.parent_report": dict(pid="pid"), "reports.report": dict(pid="pid"),
    "team.mascot_delete": dict(mid="mascot"), "team.mascot_return": dict(mid="mascot"),
    "team.note_edit": dict(nid="note"), "team.note_view": dict(nid="note"), "team.notes_delete": dict(nid="note"),
}
# kun administratorer: trænere skal afvises uanset id
ADMIN = {
    "admin.club_delete": dict(cid=1), "admin.import_template": dict(fmt="csv"), "admin.team_action": dict(tid=1, action="archive"),
    "admin.user_action": dict(uid=1, action="reset"), "admin.user_detail": dict(uid=1), "admin.view_as": dict(uid=1),
    "invites_admin.resend": dict(iid=1), "invites_admin.revoke": dict(iid=1),
}
# bevidst undtaget: token-baserede/offentlige ruter og ruter der kun viser det aktive holds egne data (runde-nummer, ingen id)
EXEMPT = {"invites.accept", "invites.check_username", "reset.link", "playerlink.form", "main.club_logo", "evaluation.eval_round", "evaluation.team", "static"}


@pytest.fixture
def setup(world):
    app, admin, ca, cb, ta, tb = world
    make_team_in(app, admin, "Alfa Klub", "Hold Alfa2")
    mia = make_user(app, admin, "mia", "trainer", "Alfa Klub", ["Hold Alfa2"])         # samme klub, andet hold
    add_player(ta, "Anna Alfa")
    pid = player_id(app, "Anna Alfa")
    tid = sql(app, "SELECT team_id FROM players WHERE id=?", pid)[0]["team_id"]
    cid = sql(app, "SELECT club_id FROM teams WHERE id=?", tid)[0]["club_id"]
    sql(app, "INSERT INTO lineups(team_id,name,game_type,formation,created_at,updated_at) VALUES(?,?,?,?,datetime('now'),datetime('now'))", tid, "L", "8v8", "3-3-1")
    sql(app, "INSERT INTO att_events(team_id,kind,day,created_by) VALUES(?,?,?,?)", tid, "match", "2026-11-01", "x")
    sql(app, "INSERT INTO team_notes(team_id,author,created_at,body) VALUES(?,?,datetime('now'),?)", tid, "x", "n")
    sql(app, "INSERT INTO mascot_log(team_id,player_id,taken_on,reason,created_by) VALUES(?,?,?,?,?)", tid, pid, "2026-11-01", "r", "x")
    sql(app, "INSERT INTO player_links(player_id,token_hash,created_at,expires_at,created_by) VALUES(?,?,1,9999999999,?)", pid, "h", "x")
    sql(app, "INSERT INTO matches(team_id,day,game_type,formation) VALUES(?,?,?,?)", tid, "2026-11-01", "8v8", "3-3-1")
    sql(app, "INSERT INTO conversations(player_id,held_on,notes) VALUES(?,?,?)", pid, "2026-11-01", "n")
    sql(app, "INSERT INTO messages(club_id,team_id,sender_name,title,body,created_at) VALUES(?,?,?,?,?,datetime('now'))", cid, tid, "x", "t", "b")
    one = lambda q: sql(app, q)[0]["id"]
    ctx = dict(pid=pid, lineup=one("SELECT id FROM lineups"), event=one("SELECT id FROM att_events"), note=one("SELECT id FROM team_notes"),
               mascot=one("SELECT id FROM mascot_log"), plink=one("SELECT id FROM player_links"), match=one("SELECT id FROM matches"),
               conv=one("SELECT id FROM conversations"), msg=one("SELECT id FROM messages"))
    return app, ctx, dict(samme_klub=mia, anden_klub=world[5])


def _call(c, rule, kwargs):
    from flask import url_for
    with c.c.application.test_request_context():
        url = url_for(rule.endpoint, **kwargs)
    out = []
    for m in sorted(rule.methods - {"HEAD", "OPTIONS"}):
        r = c.get(url) if m == "GET" else c.post(url, {}, page="/")
        out.append((m, r.status_code))
    return url, out


def test_every_id_route_is_covered(setup):
    app, ctx, who = setup
    unknown = sorted(r.endpoint for r in app.url_map.iter_rules() if "<" in r.rule and r.endpoint not in RES | ADMIN and r.endpoint not in EXEMPT)
    assert not unknown, f"Ny rute uden isolationstest – tilføj den til RES/ADMIN/EXEMPT i tests/test_isolation_routes.py: {unknown}"


@pytest.mark.parametrize("who_name", ["samme_klub", "anden_klub"])
def test_other_team_cannot_reach_resources_or_admin(setup, who_name):
    app, ctx, who = setup
    c = who[who_name]
    bad = []
    for rule in app.url_map.iter_rules():
        ep = rule.endpoint
        if ep in RES:
            kwargs = {k: (ctx[v] if isinstance(v, str) else v) for k, v in RES[ep].items()}
        elif ep in ADMIN:
            kwargs = ADMIN[ep]
        else:
            continue
        url, results = _call(c, rule, kwargs)
        for m, code in results:
            if code not in (403, 404):
                bad.append(f"{m} {url} → {code}")
    assert not bad, "Adgang på tværs af hold:\n" + "\n".join(bad)


def test_positive_control_owner_reaches_own_resources(world, setup):
    """Kontrol af selve testen: ejerholdets træner når de samme ressourcer (ellers ville alt trivielt give 404)."""
    app, ctx, who = setup
    ta = world[4]
    from flask import url_for
    ok = checked = 0
    for rule in app.url_map.iter_rules():
        ep = rule.endpoint
        if ep in RES and "GET" in rule.methods and ep not in ("players.photo_view", "players.export_json"):
            kwargs = {k: (ctx[v] if isinstance(v, str) else v) for k, v in RES[ep].items()}
            with app.test_request_context():
                url = url_for(ep, **kwargs)
            checked += 1
            ok += ta.get(url).status_code in (200, 302)
    assert checked >= 10 and ok == checked, (ok, checked)
