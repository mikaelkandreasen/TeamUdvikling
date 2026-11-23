"""Indbakke: beskeder fra klubadministrator (til hele klubben) og chef-træner (til holdet). Vises ved næste login indtil de er læst, og gemmes i indbakken."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for

from . import mail_queue, club, mailer, scope
from .db import audit, get_db
from .team import can_configure

bp = Blueprint("inbox", __name__, url_prefix="/inbox")
MAX_TITLE, MAX_BODY = 120, 3000


def _visible_sql(user):
    """WHERE-del: klubbeskeder i brugerens klub, beskeder til hold brugeren er tilknyttet (user_teams), beskeder til alle (club_id 0)
    og private svar (til brugeren eller fra brugeren)."""
    uid = user["id"]
    return ("((m.to_user_id IS NULL AND ((m.club_id = ? AND (m.team_id IS NULL OR m.team_id IN (SELECT team_id FROM user_teams WHERE user_id = ?))) OR m.club_id = 0))"
            " OR m.to_user_id = ? OR (m.to_user_id IS NOT NULL AND m.sender_id = ?))", (user["club_id"] or -1, uid, uid, uid))


def audience(db, m):
    """Modtagernes bruger-id'er for en klub-/hold-/alle-besked (afsenderen undtaget)."""
    if m["to_user_id"]:
        return [m["to_user_id"]]
    if m["club_id"] == 0:
        q, a = "SELECT id FROM users WHERE stopped_at IS NULL", ()
    elif m["team_id"]:
        q, a = "SELECT u.id FROM users u JOIN user_teams ut ON ut.user_id=u.id WHERE ut.team_id=? AND u.stopped_at IS NULL", (m["team_id"],)
    else:
        q, a = "SELECT id FROM users WHERE club_id=? AND stopped_at IS NULL", (m["club_id"],)
    return [r["id"] for r in db.execute(q, a) if r["id"] != m["sender_id"]]


def read_stats(db, msgs, uid):
    """{besked-id: (læst, ialt)} for beskeder brugeren selv har sendt."""
    out = {}
    for m in msgs:
        if m["sender_id"] == uid:
            ids = audience(db, m)
            n = db.execute(f"SELECT COUNT(*) FROM message_reads WHERE message_id=? AND user_id IN ({','.join('?' * len(ids)) or 'NULL'})", (m["id"], *ids)).fetchone()[0] if ids else 0  # nosec B608 – identifikatorer fra faste lister / kun ?-pladsholdere
            out[m["id"]] = (n, len(ids))
    return out


def for_user(db, user, only_unread=False, limit=200):
    where, args = _visible_sql(user)
    sql = ("SELECT m.*, t.name AS team_name, (r.user_id IS NOT NULL OR m.sender_id = ?) AS is_read FROM messages m LEFT JOIN teams t ON t.id=m.team_id "  # nosec B608 – identifikatorer fra faste lister / kun ?-pladsholdere
           "LEFT JOIN message_reads r ON r.message_id=m.id AND r.user_id=? WHERE " + where)
    if only_unread:
        sql += " AND r.user_id IS NULL AND COALESCE(m.sender_id,0) <> ?"
    sql += " ORDER BY m.id DESC LIMIT ?"
    a = [user["id"], user["id"], *args] + ([user["id"]] if only_unread else []) + [limit]
    return db.execute(sql, a).fetchall()


@bp.app_context_processor
def _ctx():
    if not g.get("user") or session.get("stage") != "ok" or g.get("viewing"):
        return dict(inbox_unread=[])
    return dict(inbox_unread=for_user(get_db(), g.user, only_unread=True))


def _targets():
    """Hvem brugeren må skrive til: [(værdi, tekst)]."""
    out = []
    if scope.is_sysadmin(g.user) and not g.get("viewing"):
        out.append(("all", "Alle brugere"))
    if g.user["club_id"] and scope.can_manage_club(g.user, g.user["club_id"]):
        out.append(("club", "Hele klubben"))
    if can_configure() and not g.team["archived"]:
        out.append(("team", f"Holdet {g.team['name']}"))
    return out


@bp.route("/")
def index():
    db = get_db()
    msgs = for_user(db, g.user)
    return render_template("inbox.html", msgs=msgs, targets=_targets(), MAX_BODY=MAX_BODY, stats=read_stats(db, msgs, g.real_user["id"]))


@bp.route("/send", methods=["POST"])
def send():
    db = get_db()
    targets = dict(_targets())
    kind = request.form.get("to")
    title = (request.form.get("title") or "").strip()[:MAX_TITLE]
    body = (request.form.get("body") or "").strip()[:MAX_BODY]
    if kind not in targets:
        abort(403)
    if not title or not body:
        flash("Skriv både en overskrift og en besked.", "error")
        return redirect(url_for("inbox.index"))
    team_id = g.team["id"] if kind == "team" else None
    club_id = 0 if kind == "all" else g.user["club_id"]
    cur = db.execute("INSERT INTO messages(club_id,team_id,sender_id,sender_name,title,body,created_at) VALUES(?,?,?,?,?,?,datetime('now','localtime'))",
                     (club_id, team_id, g.real_user["id"], g.user["display_name"], title, body))
    db.execute("INSERT OR IGNORE INTO message_reads(message_id,user_id,read_at) VALUES(?,?,datetime('now','localtime'))", (cur.lastrowid, g.real_user["id"]))
    audit(db, g.user["username"], "besked_sendt", f"{ {'all': 'alle', 'club': 'klub'}.get(kind) or g.team['name'] }: id={cur.lastrowid}")
    db.commit()
    flash("Beskeden er sendt.", "ok")
    if request.form.get("email"):
        _email(db, kind, team_id, title, body)
    return redirect(url_for("inbox.index"))


def _email(db, kind, team_id, title, body):
    """Sender beskeden som e-mail til modtagere med adresse (afsenderen springes over – undtagen ved «Alle brugere», hvor afsenderen også får den). Hver modtager får sin egen mail."""
    todo = mailer.missing()
    if todo:
        flash(f"Beskeden er gemt, men e-mail er ikke sat op: mangler {todo}.", "error")
        return
    if kind == "all":
        # «Alle brugere»: afsenderen (systemadministratoren) får også selv e-mailen, så man kan se, hvordan den ser ud
        rows = db.execute("SELECT DISTINCT email, id FROM users WHERE stopped_at IS NULL AND email IS NOT NULL AND email<>''").fetchall()
        where = club.info()["app_name"]
    elif kind == "club":
        rows = db.execute("SELECT DISTINCT email, id FROM users WHERE club_id=? AND stopped_at IS NULL AND email IS NOT NULL AND email<>'' AND id<>?",
                          (g.user["club_id"], g.real_user["id"])).fetchall()
        where = club.info()["name"] or "klubben"
    else:
        rows = db.execute("SELECT DISTINCT u.email, u.id FROM users u JOIN user_teams ut ON ut.user_id=u.id WHERE ut.team_id=? AND u.stopped_at IS NULL "
                          "AND u.email IS NOT NULL AND u.email<>'' AND u.id<>?", (team_id, g.real_user["id"])).fetchall()
        where = g.team["name"]
    text = f"{body}\n\n— {g.user['display_name']}, {where}\n{mailer.public_url()}/inbox/"
    subj = f"{where}: {title}".replace("\n", " ").replace("\r", " ")
    for r in rows:
        mail_queue.enqueue(db, r["email"], subj, text, "besked")
    audit(db, g.user["username"], "besked_mail", f"i_koe={len(rows)}")
    db.commit()
    flash(f"E-mail lagt i kø til {len(rows)} modtagere – sendes i baggrunden.", "ok")


def _own(db, mid):
    where, args = _visible_sql(g.user)
    m = db.execute("SELECT m.* FROM messages m WHERE m.id=? AND " + where, (mid, *args)).fetchone()  # nosec B608 – identifikatorer fra faste lister / kun ?-pladsholdere
    if not m:
        abort(404)
    return m


@bp.route("/read", methods=["POST"])
def read_all():
    db = get_db()
    mid = request.form.get("id", type=int)
    ids = [_own(db, mid)["id"]] if mid else [m["id"] for m in for_user(db, g.user, only_unread=True)]
    for i in ids:
        db.execute("INSERT OR IGNORE INTO message_reads(message_id,user_id,read_at) VALUES(?,?,datetime('now','localtime'))", (i, g.user["id"]))
    db.commit()
    return redirect(request.form.get("next") if request.form.get("next") in ("/", "/m", "/inbox/") else url_for("inbox.index"))


@bp.route("/<int:mid>/reply", methods=["POST"])
def reply(mid):
    """Privat svar til afsenderen af en besked."""
    db = get_db()
    m = _own(db, mid)
    body = (request.form.get("body") or "").strip()[:MAX_BODY]
    to = m["sender_id"]
    if not to or to == g.real_user["id"]:
        abort(400)
    if not body:
        flash("Skriv et svar.", "error")
        return redirect(url_for("inbox.index"))
    title = m["title"] if m["title"].startswith("Re: ") else ("Re: " + m["title"])[:MAX_TITLE]
    cur = db.execute("INSERT INTO messages(club_id,team_id,sender_id,sender_name,title,body,created_at,to_user_id,reply_to) VALUES(?,?,?,?,?,?,datetime('now','localtime'),?,?)",
                     (m["club_id"], None, g.real_user["id"], g.user["display_name"], title, body, to, mid))
    db.execute("INSERT OR IGNORE INTO message_reads(message_id,user_id,read_at) VALUES(?,?,datetime('now','localtime'))", (cur.lastrowid, g.real_user["id"]))
    audit(db, g.user["username"], "besked_svar", f"id={cur.lastrowid} → {mid}")
    db.commit()
    flash("Svaret er sendt til afsenderen.", "ok")
    return redirect(url_for("inbox.index"))


@bp.route("/<int:mid>/delete", methods=["POST"])
def delete(mid):
    """Afsenderen, klubadministrator (egen klub) eller chef-træner (egne holdbeskeder) kan slette."""
    db = get_db()
    m = _own(db, mid)
    ok = m["sender_id"] == g.real_user["id"] or (not m["to_user_id"] and scope.can_manage_club(g.user, m["club_id"]))
    if not ok:
        abort(403)
    db.execute("DELETE FROM messages WHERE id=?", (mid,))
    audit(db, g.user["username"], "besked_slettet", f"id={mid}")
    db.commit()
    flash("Beskeden er slettet.", "ok")
    return redirect(url_for("inbox.index"))
