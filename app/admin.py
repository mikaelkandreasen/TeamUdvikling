"""Administration: hold, brugere (med holdtilknytning), runder, backup, Excel-eksport og revisionslog."""
import io
import secrets
import time

from flask import Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import generate_password_hash

from . import activity, club, importer, mailer, model, remember, reset, reset_tokens, scope
from . import lockout
from .auth import _fresh_login, _too_many, admin_required, manager_required, revoke_session, throttled, verify_admin_code
from .db import audit, backup, club_get, club_set, create_club, create_team, default_club_id, get_db, set_setting
from .helpers import int_in, round_info, team_id

bp = Blueprint("admin", __name__, url_prefix="/admin")


HEAD_OK = {"admin.evaluations", "admin.settings"}      # runder og rundenavne må holdets chef-træner også bruge


def _head_check():
    from .team import can_configure
    if not can_configure():
        abort(403)


@bp.before_request
def _guard():
    if request.endpoint in HEAD_OK:
        return _fresh_login(_head_check, ("admin", "clubadmin", "trainer"))()
    return manager_required(lambda: None)()


@bp.route("/")
def index():
    from . import selfcheck
    if not scope.is_sysadmin(g.user):
        return _club_home(get_db())
    return render_template("admin_index.html", sysadmin=True, checks=selfcheck.run(current_app.config))


def _club_home(db):
    """Klubadministration: én side med klubbens nøgletal, hold og alt det, en klubadministrator må rette – kun egen klub."""
    cid = scope.my_club(g.user)
    if not cid:
        abort(403)
    now = int(time.time())
    one = lambda q, *a: db.execute(q, a).fetchone()[0]
    stats = dict(
        teams=one("SELECT COUNT(*) FROM teams WHERE club_id=? AND archived=0", cid),
        archived=one("SELECT COUNT(*) FROM teams WHERE club_id=? AND archived=1", cid),
        players=one("SELECT COUNT(*) FROM players p JOIN teams t ON t.id=p.team_id WHERE t.club_id=? AND p.active=1 AND t.archived=0", cid),
        trainers=one("SELECT COUNT(*) FROM users WHERE club_id=? AND role='trainer' AND readonly=0 AND stopped_at IS NULL", cid),
        assistants=one("SELECT COUNT(*) FROM users WHERE club_id=? AND role='trainer' AND readonly=1 AND stopped_at IS NULL", cid),
        admins=one("SELECT COUNT(*) FROM users WHERE club_id=? AND role='clubadmin' AND stopped_at IS NULL", cid),
        invites=one("SELECT COUNT(*) FROM invitations WHERE club_id=? AND used_at IS NULL AND revoked=0 AND expires_at>?", cid, now),
        no_2fa=one("SELECT COUNT(*) FROM users WHERE club_id=? AND totp_enabled=0 AND stopped_at IS NULL", cid),
        overdue=one("SELECT COUNT(*) FROM players p JOIN teams t ON t.id=p.team_id WHERE t.club_id=? AND p.active=0 AND p.deactivated_at IS NOT NULL", cid),
    )
    heads = {}
    for r in db.execute("SELECT th.team_id, u.display_name FROM team_heads th JOIN users u ON u.id=th.user_id JOIN teams t ON t.id=th.team_id "
                        "WHERE t.club_id=? ORDER BY u.display_name COLLATE NOCASE", (cid,)):
        heads.setdefault(r["team_id"], []).append(r["display_name"])
    teams_ = db.execute("SELECT t.id, t.name, t.season, t.archived, (SELECT COUNT(*) FROM players p WHERE p.team_id=t.id AND p.active=1) AS players, "
                        "(SELECT COUNT(*) FROM user_teams ut WHERE ut.team_id=t.id) AS trainers FROM teams t WHERE t.club_id=? "
                        "ORDER BY t.archived, t.name COLLATE NOCASE", (cid,)).fetchall()
    return render_template("admin_club_home.html", club=club_get(db, cid), stats=stats, teams_=teams_, heads=heads)


@bp.route("/testmail", methods=["POST"])
@admin_required
def testmail():
    """Sender en prøvemail til systemadministratorens egen adresse, så SMTP-opsætningen kan afprøves uden at nulstille nogen."""
    db = get_db()
    to = (g.user["email"] or "").strip()
    todo = mailer.missing()
    if todo:
        flash(f"E-mail er ikke sat op: mangler {todo}.", "error")
    elif not to:
        flash("Din bruger har ingen e-mailadresse. Tilføj den under Brugere, og prøv igen.", "error")
    else:
        try:
            mailer.send(to, "Prøvemail fra Team Udvikling", "Hvis du kan læse dette, virker e-mailopsætningen.\n")
            audit(db, g.user["username"], "testmail_sendt")
            db.commit()
            flash(f"Prøvemail sendt til {to}.", "ok")
        except Exception as exc:      # noqa: BLE001 – SMTP kan fejle på mange måder
            current_app.logger.warning("Prøvemail fejlede (%s)", type(exc).__name__)
            flash(f"Prøvemailen kunne ikke sendes ({type(exc).__name__}). Tjek SMTP-indstillingerne.", "error")
    return redirect(url_for("admin.index"))


def _visible_clubs(db):
    """Klubber den indloggede må administrere: alle (systemadministrator) eller egen."""
    if scope.is_sysadmin(g.user):
        return db.execute("SELECT * FROM clubs ORDER BY name COLLATE NOCASE, id").fetchall()
    return db.execute("SELECT * FROM clubs WHERE id=?", (g.user["club_id"],)).fetchall()


def _pick_club(db, raw):
    """Klub fra en formular, valideret mod hvad brugeren må administrere. Klubadministratorer får altid egen klub."""
    if not scope.is_sysadmin(g.user):
        return g.user["club_id"]
    if raw in (None, ""):                                 # ingen valgt (kun én klub i formularen) → aktive holds klub, ellers standardklubben
        return (g.team["club_id"] if g.get("team") else None) or default_club_id(db)
    cid = int_in(raw, 1, 10 ** 9)
    return cid if cid and db.execute("SELECT 1 FROM clubs WHERE id=?", (cid,)).fetchone() else None


# ----------------------------------------------------------------------------- klubber (kun systemadministratorer)
@bp.route("/clubs", methods=["GET", "POST"])
@admin_required
def clubs():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:80]
        if not name:
            flash("Klubnavn mangler.", "error")
        elif db.execute("SELECT 1 FROM clubs WHERE name=? COLLATE NOCASE", (name,)).fetchone():
            flash("Der findes allerede en klub med det navn.", "error")
        else:
            cid = create_club(db, name)
            audit(db, g.user["username"], "klub_oprettet", name)
            db.commit()
            flash(f"Klubben '{name}' er oprettet. Indstil udseende og invitér en klubadministrator.", "ok")
            return redirect(url_for("admin.club_profile", club=cid))
    rows = db.execute("SELECT c.*, (SELECT COUNT(*) FROM teams t WHERE t.club_id=c.id) AS teams, "
                      "(SELECT COUNT(*) FROM users u WHERE u.club_id=c.id AND u.role='trainer') AS trainers FROM clubs c ORDER BY c.name COLLATE NOCASE, c.id").fetchall()
    admins = {}
    for u in db.execute("SELECT * FROM users WHERE role='clubadmin' ORDER BY display_name COLLATE NOCASE"):
        admins.setdefault(u["club_id"], []).append(u)
    return render_template("admin_clubs.html", clubs=rows, admins=admins)


@bp.route("/clubs/<int:cid>/delete", methods=["POST"])
@admin_required
def club_delete(cid):
    db = get_db()
    c = db.execute("SELECT * FROM clubs WHERE id=?", (cid,)).fetchone()
    if not c:
        abort(404)
    if db.execute("SELECT 1 FROM teams WHERE club_id=?", (cid,)).fetchone() or db.execute("SELECT 1 FROM users WHERE club_id=?", (cid,)).fetchone():
        flash("En klub kan kun slettes, når den ikke har hold eller brugere. Slet eller flyt dem først.", "error")
    elif db.execute("SELECT COUNT(*) FROM clubs").fetchone()[0] <= 1:
        flash("Der skal altid være mindst én klub.", "error")
    elif request.form.get("confirm", "").strip() != c["name"]:
        flash("Skriv klubbens navn præcist for at bekræfte sletning.", "error")
    else:
        db.execute("DELETE FROM clubs WHERE id=?", (cid,))
        audit(db, g.user["username"], "klub_slettet", c["name"])
        db.commit()
        flash(f"Klubben '{c['name']}' er slettet.", "ok")
    return redirect(url_for("admin.clubs"))


# ----------------------------------------------------------------------------- hold
def _team_rows(db):
    sql = ("SELECT t.*, c.name AS club_name, (SELECT COUNT(*) FROM players p WHERE p.team_id=t.id) AS players, "
           "(SELECT COUNT(*) FROM user_teams ut WHERE ut.team_id=t.id) AS trainers FROM teams t LEFT JOIN clubs c ON c.id=t.club_id ")
    if scope.is_sysadmin(g.user):
        return db.execute(sql + "ORDER BY c.name COLLATE NOCASE, t.name COLLATE NOCASE").fetchall()
    return db.execute(sql + "WHERE t.club_id=? ORDER BY t.name COLLATE NOCASE", (g.user["club_id"],)).fetchall()


@bp.route("/teams", methods=["GET", "POST"])
def teams():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:80]
        cid = _pick_club(db, request.form.get("club"))
        if not cid:
            flash("Vælg en klub.", "error")
        elif not name:
            flash("Holdnavn mangler.", "error")
        elif db.execute("SELECT 1 FROM teams WHERE name=? AND club_id=?", (name, cid)).fetchone():
            flash("Der findes allerede et hold med det navn i klubben.", "error")
        else:
            create_team(db, name, request.form.get("season", "").strip()[:20], cid)
            audit(db, g.user["username"], "hold_oprettet", name)
            db.commit()
            flash(f"Holdet '{name}' er oprettet.", "ok")
            return redirect(url_for("admin.teams"))
    members = {}
    for r in db.execute("SELECT ut.team_id, u.id, u.display_name FROM user_teams ut JOIN users u ON u.id=ut.user_id ORDER BY u.display_name COLLATE NOCASE"):
        members.setdefault(r["team_id"], []).append(r)
    heads = {}
    for r in db.execute("SELECT team_id, user_id FROM team_heads"):
        heads.setdefault(r["team_id"], []).append(r["user_id"])
    return render_template("admin_teams.html", teams=_team_rows(db), clubs=_visible_clubs(db), members=members, heads=heads)


@bp.route("/teams/<int:tid>/<action>", methods=["POST"])
def team_action(tid, action):
    db = get_db()
    t = db.execute("SELECT * FROM teams WHERE id=?", (tid,)).fetchone()
    if not t or not scope.can_manage_club(g.user, t["club_id"]):
        abort(404)
    if action == "rename":
        name = request.form.get("name", "").strip()[:80]
        clash = db.execute("SELECT 1 FROM teams WHERE name=? AND club_id=? AND id<>?", (name, t["club_id"], tid)).fetchone()
        if not name or clash:
            flash("Ugyldigt eller optaget holdnavn.", "error")
        else:
            db.execute("UPDATE teams SET name=?, season=? WHERE id=?", (name, request.form.get("season", "").strip()[:20] or None, tid))
            audit(db, g.user["username"], "hold_omdøbt", f"{t['name']} -> {name}")
            flash("Gemt.", "ok")
    elif action == "delete":
        if request.form.get("confirm", "").strip() != t["name"]:
            flash("Skriv holdets navn præcist for at bekræfte sletning.", "error")
        else:
            db.execute("DELETE FROM settings WHERE key LIKE ?", (f"t{tid}:%",))
            db.execute("DELETE FROM teams WHERE id=?", (tid,))  # CASCADE: spillere, evalueringer, svar, udviklingsdata
            audit(db, g.user["username"], "hold_slettet", t["name"])
            flash(f"Holdet '{t['name']}' og alle dets data er slettet.", "ok")
    elif action in ("archive", "unarchive"):
        db.execute("UPDATE teams SET archived=? WHERE id=?", (1 if action == "archive" else 0, tid))
        audit(db, g.user["username"], "hold_arkiveret" if action == "archive" else "hold_genåbnet", t["name"])
        flash("Holdet er arkiveret (skrivebeskyttet)." if action == "archive" else "Holdet er genåbnet.", "ok")
    elif action == "head":
        valid = {r["user_id"] for r in db.execute("SELECT ut.user_id FROM user_teams ut JOIN users u ON u.id=ut.user_id WHERE ut.team_id=? AND u.club_id IS ? AND u.role='trainer' AND u.readonly=0", (tid, t["club_id"]))}
        chosen = {int(x) for x in request.form.getlist("head_user") if x.isdigit()} & valid
        db.execute("DELETE FROM team_heads WHERE team_id=?", (tid,))
        for uid in chosen:
            db.execute("INSERT INTO team_heads(team_id,user_id) VALUES(?,?)", (tid, uid))
        audit(db, g.user["username"], "cheftraenere_sat", f"{t['name']}: {len(chosen)}")
        flash("Chef-trænere gemt.", "ok")
    else:
        abort(404)
    db.commit()
    return redirect(url_for("admin.teams"))


# --------------------------------------------------------------------------- brugere
def _user_rows(db):
    if scope.is_sysadmin(g.user):
        return db.execute("SELECT u.*, c.name AS club_name FROM users u LEFT JOIN clubs c ON c.id=u.club_id WHERE u.stopped_at IS NULL ORDER BY u.username").fetchall()
    return db.execute("SELECT u.*, c.name AS club_name FROM users u LEFT JOIN clubs c ON c.id=u.club_id "
                      "WHERE u.club_id=? AND u.role<>'admin' AND u.stopped_at IS NULL ORDER BY u.username", (g.user["club_id"],)).fetchall()


def _render_users(db):
    """Overskuelig liste over alle brugere (navn, rolle, klub, hold). Detaljer og nulstilling ligger på brugerens egen side."""
    teams = {}
    for r in db.execute("SELECT ut.user_id, t.name FROM user_teams ut JOIN teams t ON t.id=ut.team_id ORDER BY t.name COLLATE NOCASE"):
        teams.setdefault(r["user_id"], []).append(r["name"])
    q = (request.args.get("q") or "").strip().lower()
    club = int_in(request.args.get("club"), 1, 10 ** 9)
    rows = []
    for u in _user_rows(db):
        if club and u["club_id"] != club:
            continue
        if q and q not in (u["display_name"] + " " + u["username"] + " " + (u["email"] or "")).lower():
            continue
        rows.append(dict(u=u, teams=teams.get(u["id"], [])))
    from . import invites
    now = int(time.time())
    invs = [dict(r, state=invites.status(r, now), sent=_fmt_ts(r["created_at"])) for r in invites._rows(db)]
    return render_template("admin_users.html", rows=rows, all_teams=_team_rows(db), clubs=_visible_clubs(db), sysadmin=scope.is_sysadmin(g.user),
                           role_label=scope.ROLE_LABEL, can_manage=lambda u: scope.can_manage_user(g.user, u), q=q, club_filter=club, total=len(_user_rows(db)), invs=invs)


def _render_user_detail(db, u, temp=None):
    mem = {r["team_id"] for r in db.execute("SELECT team_id FROM user_teams WHERE user_id=?", (u["id"],))}
    club = db.execute("SELECT name FROM clubs WHERE id=?", (u["club_id"],)).fetchone() if u["club_id"] else None
    from . import profiles as _pf
    extra = [p for p in _pf.list_for(db, u) if not p["main"]]
    return render_template("admin_user.html", u=dict(u, club_name=club["name"] if club else None), mem=mem, extra_profiles=extra, all_teams=_team_rows(db), temp=temp,
                           mail_missing=mailer.missing(), clubs=_visible_clubs(db), sysadmin=scope.is_sysadmin(g.user), role_label=scope.ROLE_LABEL,
                           last_login=_fmt_ts(u["last_login"]))


def _fmt_ts(ts):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.fromtimestamp(ts, ZoneInfo(current_app.config.get("TIMEZONE") or "UTC")).strftime("%d-%m-%Y %H:%M") if ts else ""


@bp.route("/users/<int:uid>")
def user_detail(uid):
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u or u["stopped_at"] or not scope.can_manage_user(g.user, u):
        abort(404)
    return _render_user_detail(db, u)


def _set_user_teams(db, uid, team_ids, club_id):
    """Kun hold i brugerens egen klub kan tildeles."""
    valid = {r["id"] for r in db.execute("SELECT id FROM teams WHERE club_id IS ?", (club_id,))} if club_id else set()
    db.execute("DELETE FROM user_teams WHERE user_id=? AND team_id IN (SELECT id FROM teams WHERE club_id IS ?)", (uid, club_id))
    for t in {int(x) for x in team_ids if str(x).isdigit()} & valid:
        db.execute("INSERT INTO user_teams(user_id,team_id) VALUES(?,?)", (uid, t))


@bp.route("/users/overview")
@admin_required
def users_overview():
    """Systemadministrator: alle brugere med klub, hold, oprettet og senest logget ind."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    db = get_db()
    zone = ZoneInfo(current_app.config.get("TIMEZONE") or "UTC")
    teams = {}
    for r in db.execute("SELECT ut.user_id, t.name, EXISTS(SELECT 1 FROM team_heads h WHERE h.team_id=t.id AND h.user_id=ut.user_id) AS head "
                        "FROM user_teams ut JOIN teams t ON t.id=ut.team_id ORDER BY t.name COLLATE NOCASE"):
        teams.setdefault(r["user_id"], []).append(r["name"] + (" (chef)" if r["head"] else ""))
    rows = []
    for u in db.execute("SELECT u.*, c.name AS club_name, p.last_seen FROM users u LEFT JOIN clubs c ON c.id=u.club_id "
                        "LEFT JOIN presence p ON p.user_id=u.id WHERE u.stopped_at IS NULL ORDER BY u.created_at DESC, u.id DESC"):
        fmt = lambda ts: datetime.fromtimestamp(ts, zone).strftime("%d-%m-%Y %H:%M") if ts else ""
        rows.append(dict(u=u, teams=teams.get(u["id"], []), login=fmt(u["last_login"]), seen=fmt(u["last_seen"]), role=scope.ROLE_LABEL.get(u["role"], u["role"])))
    return render_template("admin_users_overview.html", rows=rows)


@bp.route("/users", methods=["GET", "POST"])
def users():
    db = get_db()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        name = request.form.get("display_name", "").strip() or username
        role = request.form.get("role") if scope.is_sysadmin(g.user) and request.form.get("role") in scope.ROLES else "trainer"
        club_id = None if role == "admin" else _pick_club(db, request.form.get("club"))
        email, email_err = mailer.normalize_email(request.form.get("email"))
        if not username:
            flash("Brugernavn mangler.", "error")
        elif role != "admin" and not club_id:
            flash("Vælg en klub.", "error")
        elif email_err:
            flash(email_err, "error")
        elif db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            flash("Brugernavnet findes allerede.", "error")
        else:
            temp = secrets.token_urlsafe(12)
            ro = 1 if role == "trainer" and request.form.get("readonly") == "1" else 0
            cur = db.execute("INSERT INTO users(username,display_name,pw_hash,role,must_change_pw,created_at,email,club_id,readonly) VALUES(?,?,?,?,1,datetime('now'),?,?,?)",
                             (username, name, generate_password_hash(temp), role, email, club_id, ro))
            _set_user_teams(db, cur.lastrowid, request.form.getlist("teams") if role == "trainer" else [], club_id)
            audit(db, g.user["username"], "bruger_oprettet", f"{username} ({role})")
            db.commit()
            flash(f"Bruger '{username}' oprettet. Midlertidig adgangskode vises kun nu.", "ok")
            return _render_user_detail(db, db.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone(), temp)
    return _render_users(db)


GATED_USER_ACTIONS = {"role", "email", "delete", "unlock", "profile-add", "profile-remove"}


def _code_gate(db):
    """Trin-op: egen frisk 2FA-kode kræves til følsomme handlinger. None = ok, ellers et svar der skal returneres."""
    if throttled(db):
        return _too_many()
    if verify_admin_code(db, g.user, request.form.get("code", "")):
        return None
    if lockout.is_locked(db, db.execute("SELECT * FROM users WHERE id=?", (g.user["id"],)).fetchone()):
        revoke_session(db)
        db.commit()
        session.clear()
        return redirect(url_for("auth.login"))
    flash("Forkert eller allerede brugt 2FA-kode. Vent på en ny kode i appen og prøv igen.", "error")
    return redirect(url_for("admin.user_detail", uid=request.view_args["uid"]))


@bp.route("/users/<int:uid>/<action>", methods=["POST"])
def user_action(uid, action):
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u or u["stopped_at"] or not scope.can_manage_user(g.user, u):
        abort(404)
    temp = None
    if action in GATED_USER_ACTIONS:                    # I-06: følsomme ændringer kræver en frisk 2FA-kode
        bad = _code_gate(db)
        if bad is not None:
            return bad
    if action == "teams":
        if u["role"] == "admin":
            abort(400)
        _set_user_teams(db, uid, request.form.getlist("teams") if u["role"] == "trainer" else [], u["club_id"])
        flash("Holdtilknytning gemt.", "ok")
    elif action in ("profile-add", "profile-remove", "profile-teams"):
        if not scope.is_sysadmin(g.user):
            abort(404)
        club = int_in(request.form.get("club"), 1, 10 ** 9)
        if action == "profile-add":
            role = request.form.get("role")
            if role not in ("trainer", "clubadmin", "admin") or (role != "admin" and not (club and db.execute("SELECT 1 FROM clubs WHERE id=?", (club,)).fetchone())):
                flash("Vælg rolle og klub.", "error")
                return redirect(url_for("admin.user_detail", uid=uid))
            club = None if role == "admin" else club
            if (role, club) == (u["role"], u["club_id"]) or db.execute("SELECT 1 FROM user_profiles WHERE user_id=? AND role=? AND club_id IS ?", (uid, role, club)).fetchone():
                flash("Brugeren har allerede den profil.", "error")
                return redirect(url_for("admin.user_detail", uid=uid))
            db.execute("INSERT INTO user_profiles(user_id,role,club_id) VALUES(?,?,?)", (uid, role, club))
            audit(db, g.user["username"], "profil_tilfoejet", f"{u['username']}: {role}")
            flash("Profil tilføjet. Brugeren vælger profil øverst på siden.", "ok")
        elif action == "profile-remove":
            pid = int_in(request.form.get("profile"), 1, 10 ** 9)
            row = db.execute("SELECT * FROM user_profiles WHERE id=? AND user_id=?", (pid, uid)).fetchone() if pid else None
            if not row:
                abort(404)
            db.execute("DELETE FROM user_profiles WHERE id=?", (pid,))
            audit(db, g.user["username"], "profil_fjernet", f"{u['username']}: {row['role']}")
            flash("Profil fjernet.", "ok")
        else:
            if not club or not db.execute("SELECT 1 FROM user_profiles WHERE user_id=? AND role='trainer' AND club_id=?", (uid, club)).fetchone():
                abort(404)
            _set_user_teams(db, uid, request.form.getlist("teams"), club)
            flash("Holdtilknytning for profilen gemt.", "ok")
    elif action == "readonly":
        if u["role"] != "trainer":
            abort(400)
        on = 1 if request.form.get("readonly") == "1" else 0
        db.execute("UPDATE users SET readonly=? WHERE id=?", (on, uid))
        if on:
            db.execute("DELETE FROM team_heads WHERE user_id=?", (uid,))
        audit(db, g.user["username"], "assistent_sat" if on else "assistent_fjernet", u["username"])
        flash("Gemt: læseadgang (assistent)." if on else "Gemt: almindelig træner.", "ok")
    elif action == "role":
        if not scope.is_sysadmin(g.user):
            abort(404)
        role = request.form.get("role")
        cid = _pick_club(db, request.form.get("club")) if role != "admin" else None
        if role not in scope.ROLES or (role != "admin" and not cid):
            flash("Vælg rolle (og klub).", "error")
            return redirect(url_for("admin.user_detail", uid=uid))
        if u["role"] == "admin" and role != "admin" and db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] <= 1:
            flash("Der skal altid være mindst én systemadministrator.", "error")
            return redirect(url_for("admin.user_detail", uid=uid))
        if uid == g.user["id"] and role != "admin":
            flash("Du kan ikke fjerne din egen systemadministrator-rolle.", "error")
            return redirect(url_for("admin.user_detail", uid=uid))
        db.execute("UPDATE users SET role=?, club_id=? WHERE id=?", (role, cid, uid))
        if role != "trainer" or cid != u["club_id"]:
            db.execute("DELETE FROM user_teams WHERE user_id=?", (uid,))
        remember.revoke_user(db, uid)
        flash(f"Rollen er ændret til {scope.ROLE_LABEL[role].lower()}.", "ok")
    elif action == "email":
        email, err = mailer.normalize_email(request.form.get("email"))
        if err:
            flash(err, "error")
            return redirect(url_for("admin.user_detail", uid=uid))
        db.execute("UPDATE users SET email=? WHERE id=?", (email, uid))
        reset_tokens.revoke_user(db, uid)                 # afventende links gik til den gamle adresse
        flash("E-mailadresse gemt." if email else "E-mailadresse fjernet.", "ok")
    elif action == "mail-reset":
        purpose = request.form.get("purpose")
        if purpose not in ("password", "totp"):
            abort(400)
        if throttled(db):
            return _too_many()
        if not verify_admin_code(db, g.user, request.form.get("code", "")):
            if lockout.is_locked(db, db.execute("SELECT * FROM users WHERE id=?", (g.user["id"],)).fetchone()):
                revoke_session(db)
                db.commit()
                session.clear()                           # for mange forkerte koder → ud
                return redirect(url_for("auth.login"))
            flash("Forkert eller allerede brugt 2FA-kode. Vent på en ny kode i appen og prøv igen.", "error")
            return redirect(url_for("admin.user_detail", uid=uid))
        ok, msg = reset.send_reset(db, u, purpose, g.user["username"])
        audit(db, g.user["username"], "mail_nulstil_sendt" if ok else "mail_nulstil_fejlet", f"{u['username']} ({purpose})")
        db.commit()
        flash(msg, "ok" if ok else "error")
        return redirect(url_for("admin.user_detail", uid=uid))
    elif action == "reset-2fa":
        bad = _code_gate(db)
        if bad is not None:
            return bad
        db.execute("UPDATE users SET totp_secret=NULL, totp_enabled=0, last_totp_step=0 WHERE id=?", (uid,))
        db.execute("DELETE FROM recovery_codes WHERE user_id=?", (uid,))
        remember.revoke_user(db, uid)
        reset_tokens.revoke_user(db, uid)
        flash("2FA nulstillet – brugeren skal oprette den igen ved næste login.", "ok")
    elif action == "reset-password":
        bad = _code_gate(db)
        if bad is not None:
            return bad
        temp = secrets.token_urlsafe(12)
        db.execute("UPDATE users SET pw_hash=?, must_change_pw=1 WHERE id=?", (generate_password_hash(temp), uid))
        remember.revoke_user(db, uid)
        reset_tokens.revoke_user(db, uid)
        flash("Adgangskode nulstillet. Den midlertidige kode vises kun nu.", "ok")
    elif action == "unlock":
        lockout.clear(db, uid, all_ips=True)
        flash("Konto låst op.", "ok")
    elif action == "delete":
        if uid == g.user["id"]:
            flash("Du kan ikke slette dig selv.", "error")
            return redirect(url_for("admin.user_detail", uid=uid))
        if u["role"] == "admin" and db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] <= 1:
            flash("Der skal altid være mindst én systemadministrator.", "error")
            return redirect(url_for("admin.user_detail", uid=uid))
        from . import transfer
        if transfer.has_evaluations(db, uid):
            transfer.stop_user(db, u)
            flash("Træneren er stoppet: loginet er fjernet, men evalueringerne er bevaret i historikken under «… (stoppet)».", "ok")
        else:
            db.execute("DELETE FROM users WHERE id=?", (uid,))
            flash("Bruger slettet.", "ok")
    else:
        abort(404)
    audit(db, g.user["username"], f"bruger_{action}", u["username"])
    db.commit()
    if action == "delete":
        return redirect(url_for("admin.users"))
    return _render_user_detail(db, db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone(), temp)


# ------------------------------------------------------------------- indstillinger mv.
@bp.route("/settings", methods=["GET", "POST"])
def settings():
    db = get_db()
    tid = team_id()
    if request.method == "POST":
        for r in g.rounds:
            set_setting(db, tid, f"round_label_{r}", (request.form.get(f"label_{r}") or "").strip()[:60])
            d = (request.form.get(f"date_{r}") or "").strip()
            set_setting(db, tid, f"round_date_{r}", d if model.parse_date(d) else "")
        db.commit()
        flash("Gemt.", "ok")
        return redirect(url_for("admin.settings"))
    return render_template("admin_settings.html", infos=round_info(db))


@bp.route("/backup", methods=["POST"])
@admin_required
def make_backup():
    dest = backup(current_app.config["DATABASE"], current_app.config["BACKUP_DIR"])
    audit(get_db(), g.user["username"], "backup_hentet")
    get_db().commit()
    return send_file(dest, as_attachment=True, download_name="teamudvikling-backup.db")


@bp.route("/usage")
@admin_required
def usage():
    db = get_db()
    days = int_in(request.args.get("days"), 1, 180) or 30
    tid = int_in(request.args.get("team"), 1, 10 ** 9)
    if tid and not db.execute("SELECT 1 FROM teams WHERE id=?", (tid,)).fetchone():
        tid = None
    u = activity.usage(db, days, tid)
    return render_template("admin_usage.html", u=u, days=days, tid=tid, all_teams=db.execute("SELECT id, name FROM teams ORDER BY name COLLATE NOCASE").fetchall(),
                           now_online=activity.online(db, everyone=True), people=activity.users_table(db, days, tid),
                           bars=activity.bar_chart(u["by_day"]), heat=activity.heatmap(u["grid"]), label=activity.label, DAYS=activity.DAYS,
                           window=activity.ONLINE_WINDOW // 60)


@bp.route("/audit")
@admin_required
def audit_log():
    rows = get_db().execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 300").fetchall()
    return render_template("admin_audit.html", rows=rows)


def _append(ws, row):
    """Tilføj række; tekst der starter med '=' gemmes som ren tekst (beskyttelse mod formel-injektion i Excel)."""
    ws.append(row)
    for c in ws[ws.max_row]:
        if isinstance(c.value, str) and c.value[:1] in ("=", "+", "-", "@"):
            c.data_type = "s"


@bp.route("/export.xlsx")
@admin_required
def export_xlsx():
    """Excel-eksport af det aktive holds data."""
    from openpyxl import Workbook
    db = get_db()
    tid = team_id()
    wb = Workbook()
    ws = wb.active
    ws.title = "Spillere"
    _append(ws, ["Id", "Navn", "Fødselsdato", "Trøje", "Position", "Sekundær", "Position 3", "Position 4", "Fod", "Startdato", "Fokus 1", "Fokus 2", "Noter", "Aktiv"])
    for p in db.execute("SELECT * FROM players WHERE team_id=? ORDER BY name COLLATE NOCASE", (tid,)):
        _append(ws, [p["id"], p["name"], p["birth_date"], p["shirt_no"], p["position"], p["position2"], p["position3"], p["position4"], p["foot"],
                   p["start_date"], p["focus1"], p["focus2"], p["notes"], p["active"]])
    ws = wb.create_sheet("Evalueringer")
    _append(ws, ["Runde", "Spiller", "Træner", "Rolle", "Nøglefærdighed", "Score"])
    for r in db.execute("SELECT e.round, p.name pn, u.display_name un, e.crit, e.score FROM evaluations e "
                        "JOIN players p ON p.id=e.player_id JOIN users u ON u.id=e.trainer_id WHERE p.team_id=? "
                        "ORDER BY e.round, p.name, u.display_name, e.crit", (tid,)):
        c = model.CRITERIA[r["crit"]]
        _append(ws, [r["round"], r["pn"], r["un"], c["role"], c["skill"], r["score"]])
    ws = wb.create_sheet("Teamoversigt")
    _append(ws, ["Runde", "Spiller"] + model.ROLES + ["Samlet", "Enighed", "Fortolkning"])
    rounds = model.load_rounds(db, tid)
    names = {p["id"]: p["name"] for p in db.execute("SELECT id,name FROM players WHERE team_id=?", (tid,))}
    for rnd in g.rounds:
        for pid, res in sorted(rounds[rnd].items(), key=lambda kv: names.get(kv[0], "")):
            _append(ws, [rnd, names.get(pid)] + [None if v is None else round(v, 2) for v in res["roles"]] +
                      [None if res["samlet"] is None else round(res["samlet"], 2),
                       None if res["enighed"] is None else round(res["enighed"], 2), res["fortolkning"]])
    ws = wb.create_sheet("Motivation")
    _append(ws, ["Spiller", "Kategori", "Spørgsmål", "Score"])
    for r in db.execute("SELECT p.name pn, c.title, q.text, a.score FROM motivation_answers a JOIN players p ON p.id=a.player_id "
                        "JOIN motivation_questions q ON q.qidx=a.qidx AND q.team_id=p.team_id "
                        "JOIN motivation_categories c ON c.cat=q.cat AND c.team_id=p.team_id WHERE p.team_id=? ORDER BY p.name, q.qidx", (tid,)):
        _append(ws, [r["pn"], r["title"], r["text"], r["score"]])
    ws = wb.create_sheet("Udviklingsdata")
    _append(ws, ["Spiller", "Træninger", "Kampe"] + model.TRIVSEL + model.MOTORIK + ["Tiltag", "Spillerens mål", "Opfølgning", "Status"])
    for r in db.execute("SELECT p.name, d.* FROM devdata d JOIN players p ON p.id=d.player_id WHERE p.team_id=? ORDER BY p.name", (tid,)):
        _append(ws, [r["name"], r["trainings"], r["matches"], r["t1"], r["t2"], r["t3"], r["m1"], r["m2"], r["m3"], r["m4"],
                   r["tiltag"], r["eget_maal"], r["followup"], r["status"]])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    audit(db, g.user["username"], "excel_eksport", g.team["name"])
    db.commit()
    return send_file(buf, as_attachment=True, download_name=f"teamudvikling-eksport-{g.team['name']}.xlsx".replace(" ", "_").replace("/", "-"),
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


from . import admin_more  # noqa: E402,F401  (registrerer resten af administrationens routes på samme blueprint)
