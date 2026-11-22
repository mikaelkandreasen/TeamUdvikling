"""Invitationer: en administrator sender en e-mail med et personligt link, hvor den inviterede selv opretter sin bruger.

* Administratorer (system- og klubadministratorer for egen klub) og chef-trænere (for egne hold) kan sende, og de bekræfter med egen 2FA-kode (som ved nulstilling).
* Der kan inviteres som træner eller som chef-træner (får rettigheder til holdets indstillinger og må selv invitere til holdet).
* Linket virker i 7 dage og kan kun bruges én gang. Kun HMAC-hash af tokenet gemmes.
* Den inviterede vælger brugernavn, navn og adgangskode og sætter derefter 2FA op, før der gives adgang.
* Klubadministratorer kan kun invitere trænere til egne hold; systemadministratorer kan også invitere klubadministratorer.
"""
import hashlib
import hmac
import secrets
import sqlite3
import time

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from . import lockout, mail_queue, mailer, scope
from .auth import _bind, _fresh_login, _too_many, check_password_policy, record_fail, revoke_session, throttled, verify_admin_code
from .db import audit, club_get, default_club_id, get_db
from .helpers import int_in

TTL = 7 * 86400
MAX_PENDING_PER_CLUB = 200

admin_bp = Blueprint("invites_admin", __name__, url_prefix="/admin/invitations")
bp = Blueprint("invites", __name__)


def _h(token):
    return hmac.new(current_app.config["SECRET_KEY"].encode(), (token or "").encode(), hashlib.sha256).hexdigest()


def issue(db, email, role, club_id, team_ids, created_by, now=None, as_head=False, as_readonly=False):
    """Opretter en invitation (tidligere ubrugte til samme adresse i klubben tilbagekaldes). Returnerer rå token."""
    now = int(now if now is not None else time.time())
    db.execute("UPDATE invitations SET revoked=1 WHERE email=? AND club_id=? AND used_at IS NULL AND revoked=0", (email, club_id))
    token = secrets.token_urlsafe(32)
    db.execute("INSERT INTO invitations(token_hash,email,role,club_id,team_ids,created_by,created_at,expires_at,as_head,as_readonly) VALUES(?,?,?,?,?,?,?,?,?,?)",
               (_h(token), email, role, club_id, ",".join(str(t) for t in team_ids), created_by, now, now + TTL, 1 if as_head and role == "trainer" and not as_readonly else 0, 1 if as_readonly and role == "trainer" else 0))
    return token


def lookup(db, token, now=None):
    """Gyldig (ubrugt, ikke tilbagekaldt, ikke udløbet) invitation eller None. Forbruger ikke tokenet (mailscannere)."""
    if not token or len(token) > 100:
        return None
    return db.execute("SELECT * FROM invitations WHERE token_hash=? AND used_at IS NULL AND revoked=0 AND expires_at>?",
                      (_h(token), int(now if now is not None else time.time()))).fetchone()


def status(row, now=None):
    now = int(now if now is not None else time.time())
    if row["used_at"]:
        return "brugt"
    if row["revoked"]:
        return "tilbagekaldt"
    return "udløbet" if row["expires_at"] <= now else "afventer"


def _mail(db, row, token, inviter):
    info = club_get(db, row["club_id"])
    club = info["name"] or info["app_name"]
    what = "klubadministrator" if row["role"] == "clubadmin" else ("chef-træner" if row["as_head"] else ("assistent (læseadgang)" if row["as_readonly"] else "træner"))
    body = (f"Hej,\n\n{inviter} har inviteret dig som {what} i {club} ({info['app_name']}).\n\n"
            "Åbn linket, vælg brugernavn og adgangskode, og sæt to-faktor-login (2FA) op med en autentificeringsapp:\n\n"
            f"{mailer.public_url()}/invitation/{token}\n\n"
            "Linket virker i 7 dage og kan kun bruges én gang.\n"
            "Kender du ikke afsenderen, så ignorér mailen.\n")
    mail_queue.enqueue(db, row["email"], f"Invitation til {club}", body, "invitation")


def send(db, email, role, club_id, team_ids, inviter, as_head=False, as_readonly=False):
    """Opretter og sender. Returnerer (ok, besked). Kalderen har kontrolleret rettigheder og 2FA-kode."""
    todo = mailer.missing()
    if todo:
        return False, f"E-mail er ikke sat op: mangler {todo}."
    pending = db.execute("SELECT COUNT(*) FROM invitations WHERE club_id=? AND used_at IS NULL AND revoked=0 AND expires_at>?",
                         (club_id, int(time.time()))).fetchone()[0]
    if pending >= MAX_PENDING_PER_CLUB:
        return False, "Der er for mange afventende invitationer. Tilbagekald nogle først."
    token = issue(db, email, role, club_id, team_ids, inviter, as_head=as_head, as_readonly=as_readonly)
    row = db.execute("SELECT * FROM invitations WHERE token_hash=?", (_h(token),)).fetchone()
    try:
        _mail(db, row, token, inviter)
    except Exception as exc:      # noqa: BLE001 – SMTP kan fejle på mange måder; invitationen må ikke blive liggende
        db.execute("DELETE FROM invitations WHERE id=?", (row["id"],))
        db.commit()
        current_app.logger.warning("Invitationsmail kunne ikke sendes (%s)", type(exc).__name__)
        return False, f"E-mailen kunne ikke sendes ({type(exc).__name__}). Tjek SMTP-indstillingerne."
    return True, f"Invitation sendt til {email}. Linket virker i 7 dage."


# ----------------------------------------------------------------------------- administrator
def _heads():
    """Hold som den indloggede er chef-træner for (tom for administratorer)."""
    return scope.head_team_ids(get_db(), g.user)


def _check():
    if not scope.is_manager(g.user) and not _heads():
        abort(403)


@admin_bp.before_request
def _guard():
    return _fresh_login(_check, ("admin", "clubadmin", "trainer"))()


def _clubs(db):
    if scope.is_sysadmin(g.user):
        return db.execute("SELECT * FROM clubs ORDER BY name COLLATE NOCASE, id").fetchall()
    return db.execute("SELECT * FROM clubs WHERE id=?", (g.user["club_id"],)).fetchall()


def _teams(db):
    if not scope.is_manager(g.user):
        ids = sorted(_heads())
        return db.execute(f"SELECT t.*, c.name AS club_name FROM teams t JOIN clubs c ON c.id=t.club_id WHERE t.id IN ({','.join('?' * len(ids))}) ORDER BY t.name COLLATE NOCASE", ids).fetchall()  # nosec B608 – identifikatorer fra faste lister / kun ?-pladsholdere
    if scope.is_sysadmin(g.user):
        return db.execute("SELECT t.*, c.name AS club_name FROM teams t JOIN clubs c ON c.id=t.club_id ORDER BY c.name COLLATE NOCASE, t.name COLLATE NOCASE").fetchall()
    return db.execute("SELECT t.*, c.name AS club_name FROM teams t JOIN clubs c ON c.id=t.club_id WHERE t.club_id=? ORDER BY t.name COLLATE NOCASE", (g.user["club_id"],)).fetchall()


def _rows(db):
    sql = ("SELECT i.*, c.name AS club_name FROM invitations i JOIN clubs c ON c.id=i.club_id ")
    if not scope.is_manager(g.user):
        return db.execute(sql + "WHERE i.club_id=? AND i.created_by=? ORDER BY i.created_at DESC LIMIT 100", (g.user["club_id"], g.user["username"])).fetchall()
    if scope.is_sysadmin(g.user):
        return db.execute(sql + "ORDER BY i.created_at DESC LIMIT 100").fetchall()
    return db.execute(sql + "WHERE i.club_id=? ORDER BY i.created_at DESC LIMIT 100", (g.user["club_id"],)).fetchall()


def _page(db):
    now = int(time.time())
    return render_template("admin_invitations.html", rows=[dict(r, state=status(r, now)) for r in _rows(db)], clubs=_clubs(db),
                           all_teams=_teams(db), sysadmin=scope.is_sysadmin(g.user), manager=scope.is_manager(g.user), mail_missing=mailer.missing())


def _code_ok(db):
    """Kontrollerer administratorens 2FA-kode. Returnerer None hvis ok, ellers et svar."""
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
    return redirect(url_for("invites_admin.index"))


@admin_bp.route("/", methods=["GET", "POST"])
def index():
    db = get_db()
    if request.method == "GET":
        return _page(db)
    email, err = mailer.normalize_email(request.form.get("email"))
    role = request.form.get("role", "trainer")
    as_readonly = request.form.get("as_readonly") == "1" and role == "trainer"
    as_head = request.form.get("as_head") == "1" and role == "trainer" and not as_readonly
    if not scope.is_manager(g.user):
        role, as_head = "trainer", False                            # chef-trænere inviterer trænere og assistenter til egne hold (D-033)
    if role not in ("trainer", "clubadmin") or (role == "clubadmin" and not scope.is_sysadmin(g.user)):
        abort(404 if role == "clubadmin" else 400)
    raw_club = request.form.get("club")
    club_id = (int_in(raw_club, 1, 10 ** 9) if raw_club else default_club_id(db)) if scope.is_sysadmin(g.user) else g.user["club_id"]
    if not club_id or not db.execute("SELECT 1 FROM clubs WHERE id=?", (club_id,)).fetchone():
        flash("Vælg en klub.", "error")
        return redirect(url_for("invites_admin.index"))
    if err or not email:
        flash(err or "E-mailadresse mangler.", "error")
        return redirect(url_for("invites_admin.index"))
    if db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        flash("Der findes allerede en bruger med den e-mailadresse.", "error")
        return redirect(url_for("invites_admin.index"))
    valid = {r["id"] for r in db.execute("SELECT id FROM teams WHERE club_id=?", (club_id,))}
    if not scope.is_manager(g.user):
        valid &= _heads()                       # chef-trænere kan kun invitere til egne hold
    teams = sorted({int(x) for x in request.form.getlist("teams") if str(x).isdigit()} & valid) if role == "trainer" else []
    if role == "trainer" and not scope.is_manager(g.user) and not teams:
        flash("Vælg mindst ét af dine hold.", "error")
        return redirect(url_for("invites_admin.index"))
    if as_head and not teams:
        flash("Vælg det hold, personen skal være chef-træner for.", "error")
        return redirect(url_for("invites_admin.index"))
    bad = _code_ok(db)
    if bad is not None:
        return bad
    ok, msg = send(db, email, role, club_id, teams, g.user["username"], as_head, as_readonly)
    audit(db, g.user["username"], "invitation_sendt" if ok else "invitation_fejlet", f"{email} ({role}{', chef' if as_head else ''})")
    db.commit()
    flash(msg, "ok" if ok else "error")
    return redirect(url_for("invites_admin.index"))


def _own(db, iid):
    row = db.execute("SELECT * FROM invitations WHERE id=?", (iid,)).fetchone()
    if not row or (row["role"] == "clubadmin" and not scope.is_sysadmin(g.user)):
        abort(404)
    if scope.is_manager(g.user):
        if not scope.can_manage_club(g.user, row["club_id"]):
            abort(404)
    elif row["created_by"] != g.user["username"] or row["club_id"] != g.user["club_id"]:
        abort(404)
    return row


@admin_bp.route("/<int:iid>/revoke", methods=["POST"])
def revoke(iid):
    db = get_db()
    row = _own(db, iid)
    db.execute("UPDATE invitations SET revoked=1 WHERE id=? AND used_at IS NULL", (iid,))
    audit(db, g.user["username"], "invitation_tilbagekaldt", row["email"])
    db.commit()
    flash("Invitationen er tilbagekaldt – linket virker ikke længere.", "ok")
    return redirect(url_for("invites_admin.index"))


@admin_bp.route("/<int:iid>/resend", methods=["POST"])
def resend(iid):
    db = get_db()
    row = _own(db, iid)
    if row["used_at"]:
        flash("Invitationen er allerede brugt.", "error")
        return redirect(url_for("invites_admin.index"))
    if db.execute("SELECT 1 FROM users WHERE email=?", (row["email"],)).fetchone():
        flash("Der findes allerede en bruger med den e-mailadresse.", "error")
        return redirect(url_for("invites_admin.index"))
    bad = _code_ok(db)
    if bad is not None:
        return bad
    teams = [int(x) for x in row["team_ids"].split(",") if x]
    if not scope.is_manager(g.user):
        teams = [t for t in teams if t in _heads()]
        if not teams:
            abort(404)
    ok, msg = send(db, row["email"], row["role"], row["club_id"], teams, g.user["username"], bool(row["as_head"]), bool(row["as_readonly"]))
    audit(db, g.user["username"], "invitation_sendt_igen" if ok else "invitation_fejlet", row["email"])
    db.commit()
    flash(msg, "ok" if ok else "error")
    return redirect(url_for("invites_admin.index"))


# ----------------------------------------------------------------------------- den inviterede (offentlig side)
def _invalid():
    return render_template("invite_invalid.html"), 400


@bp.route("/invitation/<token>/brugernavn")
def check_username(token):
    """Live-tjek af ledigt brugernavn. Kræver et gyldigt invitationslink (ingen åben opslagstjeneste) og er begrænset pr. IP."""
    db = get_db()
    if throttled(db):
        return {"ok": False, "msg": "For mange forsøg – vent lidt."}, 429
    if not lookup(db, token):
        return {"ok": False, "msg": ""}, 400
    u = (request.args.get("u") or "").strip()[:60]
    if not u:
        return {"ok": False, "msg": ""}
    free = not db.execute("SELECT 1 FROM users WHERE username=?", (u,)).fetchone()
    return {"ok": free, "msg": "Brugernavnet er ledigt." if free else "Brugernavnet er optaget – vælg et andet."}


@bp.route("/invitation/<token>", methods=["GET", "POST"])
def accept(token):
    db = get_db()
    if throttled(db):
        return _too_many()
    row = lookup(db, token)
    if not row:
        record_fail(db)
        return _invalid()
    info = club_get(db, row["club_id"])
    ctx = dict(token=token, email=row["email"], club_name=info["name"] or info["app_name"], role=row["role"])
    if request.method == "GET":
        return render_template("invite_accept.html", **ctx)
    username = request.form.get("username", "").strip()[:60]
    name = request.form.get("display_name", "").strip()[:80] or username
    pw = request.form.get("password", "")
    if not username:
        problem = "Brugernavn mangler."
    elif db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        problem = "Brugernavnet er optaget – vælg et andet."
    elif db.execute("SELECT 1 FROM users WHERE email=?", (row["email"],)).fetchone():
        problem = "Der findes allerede en bruger med den e-mailadresse."
    elif pw != request.form.get("password2", ""):
        problem = "De to adgangskoder er ikke ens."
    else:
        problem = check_password_policy(pw, username)
    if problem:
        flash(problem, "error")
        return render_template("invite_accept.html", username=username, display_name=name, **ctx)
    try:
        used = db.execute("UPDATE invitations SET used_at=? WHERE id=? AND used_at IS NULL AND revoked=0 AND expires_at>?",
                          (int(time.time()), row["id"], int(time.time())))
        if used.rowcount != 1:                    # en anden anmodning nåede først (engangslink)
            db.rollback()
            return _invalid()
        cur = db.execute("INSERT INTO users(username,display_name,pw_hash,role,must_change_pw,created_at,email,club_id,readonly) "
                         "VALUES(?,?,?,?,0,datetime('now'),?,?,?)", (username, name, generate_password_hash(pw), row["role"], row["email"], row["club_id"], row["as_readonly"]))
        uid = cur.lastrowid
        if row["role"] == "trainer":
            for t in [int(x) for x in row["team_ids"].split(",") if x]:
                if db.execute("SELECT 1 FROM teams WHERE id=? AND club_id=?", (t, row["club_id"])).fetchone():
                    db.execute("INSERT OR IGNORE INTO user_teams(user_id,team_id) VALUES(?,?)", (uid, t))
                    if row["as_head"]:
                        db.execute("INSERT OR IGNORE INTO team_heads(team_id,user_id) VALUES(?,?)", (t, uid))
        db.execute("UPDATE invitations SET user_id=? WHERE id=?", (uid, row["id"]))
        audit(db, username, "invitation_brugt", f"{row['email']} ({row['role']}) inviteret af {row['created_by']}")
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        flash("Brugernavnet er optaget – vælg et andet.", "error")
        return render_template("invite_accept.html", username=username, display_name=name, **ctx)
    session.clear()
    session["uid"] = uid
    session["seen"] = int(time.time())
    _bind(db.execute("SELECT pw_hash FROM users WHERE id=?", (uid,)).fetchone()[0])
    session["stage"] = "needs_setup"
    return redirect(url_for("auth.twofa_setup"))
