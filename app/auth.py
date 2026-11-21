"""Login: adgangskode + obligatorisk TOTP-2FA, gendannelseskoder, lockout og første-gangs opsætning."""
import hashlib
import hmac
import io
import os
import secrets
import time
from functools import wraps

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for)
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash

from . import lockout, remember, reset_tokens, totp
from .db import audit, backup_if_due, club_get, get_db, purge_old

bp = Blueprint("auth", __name__)
MAX_FAILS = 5
LOCK_SECONDS = 600
MIN_PW = 12
MAX_PW = 1024              # længere input afvises uden at hashe (CPU-DoS)
MAX_USERNAME = 150
IDLE_SECONDS = 45 * 60
_DUMMY_HASH = generate_password_hash("dummy-password-for-timing")

IP_MAX_FAILS = 20          # fejlede forsøg pr. IP pr. IP_WINDOW (beskytter mod password spraying og låse-DoS)
IP_WINDOW = 600
PUBLIC = {"auth.login", "auth.login_2fa", "auth.setup", "static", "healthz", "main.club_logo", "main.privacy", "reset.link", "invites.accept", "invites.check_username"}
PRE_2FA = {"auth.login_2fa", "auth.twofa_setup", "auth.logout", "auth.force_password"}


def current_user():
    return g.get("user")


ADMIN_FRESH = 8 * 3600     # administration kræver fuldt login (kode/2FA) inden for de seneste 8 timer


def _role_required(*roles):
    def deco(view):
        return _fresh_login(view, roles)
    return deco


def _fresh_login(view, roles):
    @wraps(view)
    def wrapped(*a, **kw):
        if not g.user or g.user["role"] not in roles:
            abort(403)
        if time.time() - session.get("auth_at", 0) > ADMIN_FRESH:       # husket enhed: trin-op
            remember.revoke_current(get_db())
            revoke_session(get_db())
            get_db().commit()
            session.clear()
            flash("Administration kræver, at du logger ind igen med adgangskode og kode.", "info")
            return redirect(url_for("auth.login", next=request.path if request.method == "GET" else None))
        return view(*a, **kw)
    return wrapped


def admin_required(view):
    """Kun systemadministratorer."""
    return _fresh_login(view, ("admin",))


def manager_required(view):
    """Systemadministratorer og klubadministratorer (sidstnævnte afgrænses til egen klub i selve visningerne)."""
    return _fresh_login(view, ("admin", "clubadmin"))


def _key():
    return current_app.config["SECRET_KEY"].encode()


def _pwv(pw_hash):
    """Sessionsbinding: ændres adgangskoden, dør alle eksisterende sessioner (stjålne cookies)."""
    return hmac.new(_key(), pw_hash.encode(), hashlib.sha256).hexdigest()[:24]


def _bind(pw_hash):
    session["pwv"] = _pwv(pw_hash)
    session.setdefault("sid", secrets.token_urlsafe(24))


def _safe_next(nxt):
    if not nxt or not nxt.startswith("/") or nxt.startswith("//") or "\\" in nxt or any(ord(c) < 32 for c in nxt):
        return ""
    return nxt


client_ip = lockout.client_ip


def _sid_hash(sid):
    return hmac.new(_key(), sid.encode(), hashlib.sha256).hexdigest()


def revoke_session(db):
    """Log ud gør også en kopieret session-cookie ugyldig (sessioner er ellers signerede, statsløse cookies)."""
    sid = session.get("sid")
    if sid:
        life = int(current_app.config["PERMANENT_SESSION_LIFETIME"].total_seconds()) + 3600
        db.execute("INSERT OR IGNORE INTO revoked_sessions(sid_hash,expires_at) VALUES(?,?)", (_sid_hash(sid), int(time.time()) + life))


def consume_totp_step(db, user_id, step):
    """Atomisk: et tidstrin kan kun bruges én gang, selv ved to samtidige forespørgsler med samme kode."""
    return db.execute("UPDATE users SET last_totp_step=? WHERE id=? AND last_totp_step<?", (step, user_id, step)).rowcount == 1


def throttled(db):
    n = db.execute("SELECT COUNT(*) FROM login_attempts WHERE ip=? AND ts>?", (client_ip(), int(time.time()) - IP_WINDOW)).fetchone()[0]
    return n >= IP_MAX_FAILS


def record_fail(db):
    db.execute("INSERT INTO login_attempts(ip,ts) VALUES(?,?)", (client_ip(), int(time.time())))
    db.commit()


def _too_many():
    return ("For mange mislykkede forsøg fra din forbindelse. Vent et par minutter og prøv igen.", 429, {"Retry-After": str(IP_WINDOW)})


def _valid_session_user(db):
    row = db.execute("SELECT * FROM users WHERE id=?", (session["uid"],)).fetchone() if session.get("uid") else None
    sid = session.get("sid")
    ok = (row and sid and time.time() - session.get("seen", 0) < IDLE_SECONDS
          and hmac.compare_digest(session.get("pwv", ""), _pwv(row["pw_hash"]))
          and not db.execute("SELECT 1 FROM revoked_sessions WHERE sid_hash=?", (_sid_hash(sid),)).fetchone()
          and not (session.get("stage") == "ok" and not row["totp_enabled"]))   # 2FA nulstillet → ud
    return row if ok else None


def load_user():
    g.user = None
    db = get_db()
    row = _valid_session_user(db)
    if row is None:
        if session.get("uid"):
            session.clear()
        if remember.try_restore(db):                      # husket enhed → ny fuld session uden kode
            row = _valid_session_user(db)
    if row is None:
        return
    g.user = row
    session["seen"] = int(time.time())
    vid = session.get("view_as")
    if vid and row["role"] in ("admin", "clubadmin"):     # administrator ser siden som en træner (skrivebeskyttet)
        t = db.execute("SELECT * FROM users WHERE id=? AND role='trainer'", (vid,)).fetchone()
        if t and (row["role"] == "admin" or t["club_id"] == row["club_id"]):
            g.admin_user, g.user, g.viewing = row, t, True
        else:
            session.pop("view_as", None)
    else:
        session.pop("view_as", None)


def gate():
    """before_request: kræv fuldt login (inkl. 2FA) for alt andet end offentlige sider."""
    ep = request.endpoint
    if ep in PUBLIC or ep is None:
        return None
    if not g.user:
        return redirect(url_for("auth.login", next=request.path if request.method == "GET" else None))
    stage = session.get("stage")
    if stage != "ok":
        if ep in PRE_2FA:
            return None
        return redirect(url_for("auth.login_2fa") if stage == "pw_ok" else url_for("auth.twofa_setup"))
    if g.user["must_change_pw"] and ep not in PRE_2FA and not g.get("viewing"):
        return redirect(url_for("auth.force_password"))
    if not g.get("team") and not ep.startswith(("auth.", "admin.", "main.no_team", "main.switch_team")):
        return redirect(url_for("main.no_team"))
    return None


def _norm_code(code):
    return code.strip().lower().replace("-", "")


def _hash_code(code):
    """Nøglet hash (HMAC) – en lækket database alene kan ikke bruges til at gætte gendannelseskoder offline."""
    return hmac.new(_key(), _norm_code(code).encode(), hashlib.sha256).hexdigest()


def new_recovery_codes(db, uid, n=8):
    db.execute("DELETE FROM recovery_codes WHERE user_id=?", (uid,))
    codes = []
    for _ in range(n):
        c = secrets.token_hex(6)
        codes.append(f"{c[:4]}-{c[4:8]}-{c[8:]}")
        db.execute("INSERT INTO recovery_codes(user_id,code_hash) VALUES(?,?)", (uid, _hash_code(c)))
    return codes


def check_password_policy(pw, username=""):
    if len(pw) < MIN_PW:
        return f"Adgangskoden skal være mindst {MIN_PW} tegn."
    if len(pw) > MAX_PW:
        return f"Adgangskoden må højst være {MAX_PW} tegn."
    if username and username.lower() in pw.lower():
        return "Adgangskoden må ikke indeholde brugernavnet."
    if len(set(pw)) < 5:
        return "Adgangskoden er for ensartet."
    return None


def _fail(db, user):
    locked = lockout.register_fail(db, user)
    audit(db, user["username"], "login_fejl", "låst" if locked else "")
    db.commit()


def _ok(db, user):
    lockout.clear(db, user["id"])
    db.commit()


def verify_admin_code(db, user, code):
    """Trin-op: kræver en frisk 2FA-kode fra den indloggede bruger (replay-beskyttet). Fejl tæller som mislykket login
    (kontolåsning + IP-spærre), så en kapret session ikke kan gætte koden."""
    step = totp.verify(user["totp_secret"], code, user["last_totp_step"])
    if step and consume_totp_step(db, user["id"], step):
        db.commit()
        return True
    _fail(db, user)
    record_fail(db)
    return False


def _finish_login(db, user, remember_device=False):
    session["stage"] = "ok"
    session["seen"] = int(time.time())
    session["auth_at"] = int(time.time())
    db.execute("UPDATE users SET last_login=? WHERE id=?", (int(time.time()), user["id"]))
    if remember_device:
        remember.issue(db, user)
    audit(db, user["username"], "login")
    db.commit()
    try:
        purge_old(db)
        backup_if_due(current_app.config["DATABASE"], current_app.config["BACKUP_DIR"])
    except Exception:  # backup/oprydning må aldrig blokere et login
        current_app.logger.exception("Automatisk backup/oprydning fejlede")


@bp.route("/login", methods=["GET", "POST"])
def login():
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        return redirect(url_for("auth.setup"))
    if request.method == "POST":
        if throttled(db):
            return _too_many()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        oversize = len(username) > MAX_USERNAME or len(password) > MAX_PW
        user = None if oversize else db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        generic = "Forkert brugernavn eller adgangskode, eller kontoen er midlertidigt låst."
        if not user:
            check_password_hash(_DUMMY_HASH, password[:MAX_PW])
            record_fail(db)
            flash(generic, "error")
        else:
            locked = lockout.is_locked(db, user)
            good = check_password_hash(user["pw_hash"], password)       # altid beregnet: låst/ulåst/ukendt tager lige lang tid
        if user and (locked or not good):
            if not locked:
                _fail(db, user)
            record_fail(db)
            flash(generic, "error")
        elif user:
            _ok(db, user)
            session.clear()
            session["uid"] = user["id"]
            session["seen"] = int(time.time())
            _bind(user["pw_hash"])
            session["stage"] = "pw_ok" if user["totp_enabled"] else "needs_setup"
            session["next"] = _safe_next(request.args.get("next", ""))
            return redirect(url_for("auth.login_2fa") if user["totp_enabled"] else url_for("auth.twofa_setup"))
    return render_template("login.html")


@bp.route("/login/2fa", methods=["GET", "POST"])
def login_2fa():
    if not g.user or session.get("stage") != "pw_ok":
        return redirect(url_for("auth.login"))
    db = get_db()
    user = g.user
    if request.method == "POST":
        if throttled(db):
            return _too_many()
        code = request.form.get("code", "")
        if lockout.is_locked(db, user):
            flash("Kontoen er midlertidigt låst. Prøv igen senere.", "error")
        else:
            step = totp.verify(user["totp_secret"], code, user["last_totp_step"])
            if step and consume_totp_step(db, user["id"], step):
                _ok(db, user)
                _finish_login(db, user, request.form.get("remember") == "1")
                nxt = session.pop("next", "")
                return redirect(nxt or url_for("main.home"))
            rc = db.execute("SELECT id FROM recovery_codes WHERE user_id=? AND used=0 AND code_hash=?",
                            (user["id"], _hash_code(code))).fetchone() if len(_norm_code(code)) == 12 else None
            if rc:
                db.execute("UPDATE recovery_codes SET used=1 WHERE id=?", (rc["id"],))
                audit(db, user["username"], "gendannelseskode_brugt")
                _ok(db, user)
                _finish_login(db, user, request.form.get("remember") == "1")
                flash("Gendannelseskode brugt. Overvej at oprette nye koder under Min konto.", "info")
                return redirect(url_for("main.home"))
            _fail(db, user)
            record_fail(db)
            flash("Forkert kode.", "error")
            if lockout.is_locked(db, db.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()):
                revoke_session(db)
                db.commit()
                session.clear()
                return redirect(url_for("auth.login"))
    return render_template("login_2fa.html", remember_days=remember.days(), is_admin=user["role"] in ("admin", "clubadmin"))


def _qr_svg(uri):
    try:
        import qrcode
        import qrcode.image.svg
        img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
        buf = io.BytesIO()
        img.save(buf)
        svg = buf.getvalue().decode()
        return Markup(svg[svg.index("<svg"):])
    except Exception:  # qrcode ikke installeret → vis kun hemmelig nøgle
        return None


@bp.route("/2fa/setup", methods=["GET", "POST"])
def twofa_setup():
    if not g.user:
        return redirect(url_for("auth.login"))
    db = get_db()
    user = g.user
    if session.get("stage") == "ok" and user["totp_enabled"] and request.method == "GET" and not request.args.get("ny"):
        return redirect(url_for("auth.account"))
    if session.get("stage") == "pw_ok":
        return redirect(url_for("auth.login_2fa"))
    secret = session.get("pending_secret")
    if not secret:
        secret = session["pending_secret"] = totp.new_secret()
    if request.method == "POST":
        step = totp.verify(secret, request.form.get("code", ""))
        if step:
            db.execute("UPDATE users SET totp_secret=?, totp_enabled=1, last_totp_step=? WHERE id=?", (secret, step, user["id"]))
            codes = new_recovery_codes(db, user["id"])
            audit(db, user["username"], "2fa_aktiveret")
            db.commit()
            session.pop("pending_secret", None)
            first = session.get("stage") != "ok"
            _finish_login(db, user) if first else None
            return render_template("recovery_codes.html", codes=codes)
        flash("Koden passer ikke. Tjek at telefonens ur er korrekt, og prøv igen.", "error")
    uri = totp.otpauth_uri(secret, user["username"], club_get(db)["app_name"])
    return render_template("twofa_setup.html", secret=secret, uri=uri, qr=_qr_svg(uri))


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    """Første opsætning: opretter den første administrator. Kun mulig når der ingen brugere er."""
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        return redirect(url_for("auth.login"))
    token = current_app.config.get("SETUP_TOKEN", "")      # altid sat (miljøvariabel eller engangskode i /data/setup_token)
    if request.method == "POST":
        if throttled(db):
            return _too_many()
        username = request.form.get("username", "").strip()
        name = request.form.get("display_name", "").strip() or username
        pw = request.form.get("password", "")
        problem = None
        if not token or not hmac.compare_digest(request.form.get("setup_token", "").strip(), token):
            record_fail(db)
            problem = "Forkert opsætningskode."
        elif not username:
            problem = "Brugernavn mangler."
        elif pw != request.form.get("password2", ""):
            problem = "De to adgangskoder er ikke ens."
        else:
            problem = check_password_policy(pw, username)
        if problem:
            flash(problem, "error")
        else:
            cur = db.execute("INSERT INTO users(username,display_name,pw_hash,role,created_at) VALUES(?,?,?,?,datetime('now'))",
                             (username, name, generate_password_hash(pw), "admin"))
            audit(db, username, "admin_oprettet")
            db.commit()
            session.clear()
            session["uid"] = cur.lastrowid
            session["seen"] = int(time.time())
            _bind(db.execute("SELECT pw_hash FROM users WHERE id=?", (cur.lastrowid,)).fetchone()[0])
            session["stage"] = "needs_setup"
            try:
                os.remove(os.path.join(current_app.config["U11_DATA_DIR"], "setup_token"))   # engangskode
            except OSError:
                pass
            return redirect(url_for("auth.twofa_setup"))
    return render_template("setup.html", need_token=True)


@bp.route("/view-as/stop", methods=["POST"])
def view_as_stop():
    """Afslut 'se som træner' og gå tilbage til administratorens egen visning."""
    if g.get("viewing"):
        audit(get_db(), g.admin_user["username"], "se_som_traener_slut", g.user["username"])
        get_db().commit()
    session.pop("view_as", None)
    return redirect(url_for("admin.users"))


@bp.route("/logout", methods=["POST"])
def logout():
    if g.user:
        audit(get_db(), g.user["username"], "logout")
        get_db().commit()
    remember.revoke_current(get_db())
    revoke_session(get_db())
    get_db().commit()
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/account", methods=["GET", "POST"])
def account():
    db = get_db()
    user = g.user
    if request.method == "POST":
        action = request.form.get("action")
        if action == "password":
            if not check_password_hash(user["pw_hash"], request.form.get("old", "")):
                flash("Nuværende adgangskode er forkert.", "error")
            elif request.form.get("new", "") != request.form.get("new2", ""):
                flash("De to nye adgangskoder er ikke ens.", "error")
            else:
                problem = check_password_policy(request.form.get("new", ""), user["username"])
                if problem:
                    flash(problem, "error")
                else:
                    newhash = generate_password_hash(request.form["new"])
                    db.execute("UPDATE users SET pw_hash=?, must_change_pw=0 WHERE id=?", (newhash, user["id"]))
                    audit(db, user["username"], "adgangskode_skiftet")
                    remember.revoke_user(db, user["id"])        # alle husk-enheder skal logge ind igen
                    reset_tokens.revoke_user(db, user["id"])    # afventende nulstillingslinks dør
                    db.commit()
                    _bind(newhash)                      # denne session består; alle andre dør
                    flash("Adgangskoden er skiftet.", "ok")
        elif action == "forget_devices":
            remember.revoke_user(db, user["id"])
            audit(db, user["username"], "husk_enheder_glemt")
            db.commit()
            flash("Alle husk-enheder er glemt. De skal logge ind med kode næste gang.", "ok")
        elif action == "recovery":
            if not check_password_hash(user["pw_hash"], request.form.get("old", "")):
                flash("Adgangskode er forkert.", "error")
            else:
                codes = new_recovery_codes(db, user["id"])
                audit(db, user["username"], "nye_gendannelseskoder")
                db.commit()
                return render_template("recovery_codes.html", codes=codes)
        return redirect(url_for("auth.account"))
    left = db.execute("SELECT COUNT(*) FROM recovery_codes WHERE user_id=? AND used=0", (user["id"],)).fetchone()[0]
    return render_template("account.html", codes_left=left, devices=remember.count(db, user["id"]))


@bp.route("/account/password", methods=["GET", "POST"])
def force_password():
    """Tvungen skift af midlertidig adgangskode (efter oprettelse/nulstilling af administrator)."""
    db = get_db()
    user = g.user
    if request.method == "POST":
        if request.form.get("new", "") != request.form.get("new2", ""):
            flash("De to adgangskoder er ikke ens.", "error")
        else:
            problem = check_password_policy(request.form.get("new", ""), user["username"])
            if problem:
                flash(problem, "error")
            elif check_password_hash(user["pw_hash"], request.form["new"]):
                flash("Vælg en anden adgangskode end den midlertidige.", "error")
            else:
                newhash = generate_password_hash(request.form["new"])
                db.execute("UPDATE users SET pw_hash=?, must_change_pw=0 WHERE id=?", (newhash, user["id"]))
                audit(db, user["username"], "adgangskode_skiftet")
                remember.revoke_user(db, user["id"])
                reset_tokens.revoke_user(db, user["id"])
                db.commit()
                _bind(newhash)
                return redirect(url_for("main.home"))
    return render_template("force_password.html")
