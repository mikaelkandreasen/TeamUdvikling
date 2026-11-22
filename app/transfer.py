"""Spillere der skifter hold, og trænere der stopper: evalueringer og data bevares som historik."""
import time

from . import model
from .db import audit, get_setting
from .teams import team_rounds


def stop_user(db, u):
    """Blød sletning: loginet fjernes, men brugerens evalueringer bevares under navnet «Navn (stoppet)», så udviklingen kan følges."""
    uid = u["id"]
    name = u["display_name"] if u["display_name"].endswith("(stoppet)") else f"{u['display_name']} (stoppet)"
    for tbl in ("user_teams", "team_heads", "user_profiles", "recovery_codes", "remember_tokens", "reset_tokens", "presence", "activity", "login_fails"):
        db.execute(f"DELETE FROM {tbl} WHERE user_id=?", (uid,))
    db.execute("UPDATE users SET username=?, display_name=?, pw_hash='!stoppet', totp_secret=NULL, totp_enabled=0, email=NULL, must_change_pw=0, "
               "readonly=1, role='trainer', stopped_at=? WHERE id=?", (f"stoppet-{uid}", name, int(time.time()), uid))


def has_evaluations(db, uid):
    return bool(db.execute("SELECT (SELECT COUNT(*) FROM evaluations WHERE trainer_id=?1) + (SELECT COUNT(*) FROM level_ratings WHERE trainer_id=?1)"
                           " + (SELECT COUNT(*) FROM dbu_checks WHERE trainer_id=?1)", (uid,)).fetchone()[0])


def move_player(db, p, to_team, actor):
    """Flytter spilleren til et andet hold. Evalueringerne følger med som historik (ses i profilen under tidligere hold); resten (niveau, billede,
    motivation, udviklingsdata, noter) følger spilleren. Holdets egne runder/opstillinger ryddes for spilleren."""
    pid, frm = p["id"], p["team_id"]
    team_name = db.execute("SELECT name FROM teams WHERE id=?", (frm,)).fetchone()["name"]
    labels = {r: (get_setting(db, frm, f"round_label_{r}") or f"Evaluering {r}", get_setting(db, frm, f"round_date_{r}") or None) for r in team_rounds(db, frm)}
    now = time.strftime("%Y-%m-%d")

    def put(rnd, trainer, kind, k, v):
        lab, day = labels.get(rnd, (f"Evaluering {rnd}", None))
        db.execute("INSERT INTO eval_history(player_id,team_name,moved_at,round_no,round_label,round_date,trainer_name,kind,k,v) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (pid, team_name, now, rnd, lab, day, trainer, kind, str(k), str(v)))
    for r in db.execute("SELECT e.round, u.display_name n, e.crit, e.score FROM evaluations e JOIN users u ON u.id=e.trainer_id WHERE e.player_id=?", (pid,)).fetchall():
        put(r["round"], r["n"], "crit", r["crit"], r["score"])
    for r in db.execute("SELECT l.round, u.display_name n, l.level FROM level_ratings l JOIN users u ON u.id=l.trainer_id WHERE l.player_id=?", (pid,)).fetchall():
        put(r["round"], r["n"], "level", "", r["level"])
    for r in db.execute("SELECT d.round, u.display_name n, d.item FROM dbu_checks d JOIN users u ON u.id=d.trainer_id WHERE d.player_id=?", (pid,)).fetchall():
        put(r["round"], r["n"], "dbu", r["item"], 1)
    for tbl in ("evaluations", "level_ratings", "dbu_checks"):
        db.execute(f"DELETE FROM {tbl} WHERE player_id=?", (pid,))
    db.execute("DELETE FROM lineup_slots WHERE player_id=?", (pid,))
    db.execute("DELETE FROM player_links WHERE player_id=?", (pid,))
    db.execute("UPDATE players SET team_id=? WHERE id=?", (to_team["id"], pid))
    audit(db, actor, "spiller_flyttet", f"id={pid}: {team_name} → {to_team['name']}")


def history(db, pid):
    """Evalueringer fra tidligere hold: [{team, rounds: [{label, date, samlet, roles, trainers}]}] – nyeste hold først."""
    groups = {}
    for r in db.execute("SELECT * FROM eval_history WHERE player_id=? AND kind='crit' ORDER BY id", (pid,)):
        g_ = groups.setdefault((r["moved_at"], r["team_name"]), {})
        rd = g_.setdefault(r["round_no"], dict(label=r["round_label"], date=r["round_date"], rows=[], trainers={}))
        tid = rd["trainers"].setdefault(r["trainer_name"], len(rd["trainers"]) + 1)
        rd["rows"].append((pid, tid, int(r["k"]), int(r["v"])))
    out = []
    for (moved, team), rounds in sorted(groups.items(), reverse=True):
        items = []
        for no in sorted(rounds):
            rd = rounds[no]
            res = model.compute_round(rd["rows"]).get(pid)
            if res and res["samlet"] is not None:
                items.append(dict(label=rd["label"], date=rd["date"], samlet=res["samlet"], roles=res["roles"], trainers=sorted(rd["trainers"])))
        if items:
            out.append(dict(team=team, moved=moved, rounds=items))
    return out
