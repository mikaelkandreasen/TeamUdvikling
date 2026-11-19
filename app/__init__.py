"""Team Udvikling – Flask-app til spillerudvikling (DBU-roller x nøglefærdigheder)."""
import hmac
import os
import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, abort, g, jsonify, request, session
from werkzeug.middleware.proxy_fix import ProxyFix

from . import activity, auth, charts, club, db, helpers, model, photos, remember, teams

ROOT = Path(__file__).resolve().parent.parent


def read_version():
    try:
        return (ROOT / "VERSION").read_text().strip()
    except OSError:
        return "0.0.0"


def _secret_key(data_dir):
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    path = Path(data_dir) / "secret_key"
    if not path.exists():
        path.write_text(secrets.token_hex(32))
        path.chmod(0o600)
    return path.read_text().strip()


def _setup_token(data_dir):
    """Engangskode til første opsætning, så ingen fremmed kan oprette den første administrator."""
    path = Path(data_dir) / "setup_token"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(24))
        path.chmod(0o600)
    return path.read_text().strip()


def create_app(config=None):
    app = Flask(__name__)
    data_dir = os.environ.get("U11_DATA_DIR", str(ROOT / "data"))
    app.config.update(
        U11_DATA_DIR=data_dir,
        DATABASE=os.path.join(data_dir, "u11.db"),
        BACKUP_DIR=os.path.join(data_dir, "backups"),
        SETUP_TOKEN=os.environ.get("SETUP_TOKEN", ""),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
        SESSION_COOKIE_NAME="__Host-u11" if os.environ.get("COOKIE_SECURE", "0") == "1" else "session",
        TRUSTED_PROXIES=int(os.environ.get("TRUSTED_PROXIES", "0") or 0),
        REMEMBER_DAYS=int(os.environ.get("REMEMBER_DAYS", "30") or 0),
        SMTP_HOST=os.environ.get("SMTP_HOST", ""),
        SMTP_PORT=os.environ.get("SMTP_PORT", ""),
        SMTP_USER=os.environ.get("SMTP_USER", ""),
        SMTP_PASSWORD=os.environ.get("SMTP_PASSWORD", ""),
        SMTP_FROM=os.environ.get("SMTP_FROM", ""),
        TIMEZONE=os.environ.get("TZ", "Europe/Copenhagen"),
        SMTP_SECURITY=os.environ.get("SMTP_SECURITY", "starttls"),
        PUBLIC_URL=os.environ.get("PUBLIC_URL", ""),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=1024 * 1024,
        VERSION=read_version(),
    )
    if config:
        app.config.update(config)
    os.makedirs(app.config["U11_DATA_DIR"], exist_ok=True)
    app.config.setdefault("SECRET_KEY", _secret_key(app.config["U11_DATA_DIR"]))
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = _secret_key(app.config["U11_DATA_DIR"])
    db.init_db(app.config["DATABASE"])
    if app.config["TRUSTED_PROXIES"]:      # kun bag en reverse proxy du styrer: giver ægte klient-IP og https-skema
        n = app.config["TRUSTED_PROXIES"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=0)
    con = db.connect(app.config["DATABASE"])
    no_users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    con.close()
    if no_users and not app.config.get("SETUP_TOKEN"):
        app.config["SETUP_TOKEN"] = _setup_token(app.config["U11_DATA_DIR"])
        app.logger.warning("FØRSTE OPSÆTNING: opsætningskoden står i %s/setup_token (og vises ikke igen).", app.config["U11_DATA_DIR"])

    if app.config["SESSION_COOKIE_SECURE"] and not app.config["TRUSTED_PROXIES"]:
        app.logger.warning("COOKIE_SECURE=1 men TRUSTED_PROXIES=0: appen ser kun proxyens IP, så alle brugere deler én IP-spærre. "
                           "Sæt TRUSTED_PROXIES=1 bag Cloudflare/reverse proxy.")

    app.teardown_appcontext(db.close_db)

    @app.before_request
    def _limits():                                # billedupload må være større end resten (sættes før formularen læses)
        if request.endpoint == "players.photo_upload":
            request.max_content_length = photos.MAX_UPLOAD + 256 * 1024

    @app.before_request
    def _before():
        session.permanent = True
        auth.load_user()
        teams.resolve(db.get_db(), g.get("user"))
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
            if not sent or not hmac.compare_digest(sent, session.get("csrf", "")):
                abort(400, "Ugyldig eller udløbet formular (CSRF). Gå tilbage, genindlæs siden og prøv igen.")
        blocked = auth.gate()
        if blocked is not None:
            return blocked
        if g.get("viewing") and request.method not in ("GET", "HEAD", "OPTIONS") and request.endpoint not in (
                "auth.view_as_stop", "auth.logout", "main.switch_team"):
            abort(403, "Skrivebeskyttet visning: afslut 'se som træner' for at ændre noget.")
        activity.touch()
        return None

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()")
        resp.headers.setdefault("X-Robots-Tag", "noindex, nofollow, noarchive")        # siden er privat – ingen søgemaskiner
        resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        resp.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        remember.apply_cookie(resp)
        if app.config["SESSION_COOKIE_SECURE"]:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        resp.headers.setdefault("Content-Security-Policy",
                                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                "script-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'")
        if request.endpoint == "main.club_logo":
            resp.headers["Cache-Control"] = "public, max-age=3600"
        elif request.endpoint != "static":
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.context_processor
    def _ctx():
        def csrf_token():
            if "csrf" not in session:
                session["csrf"] = secrets.token_urlsafe(32)
            return session["csrf"]
        return dict(csrf_token=csrf_token, user=g.get("user"), team=g.get("team"), teams=g.get("teams", []), club=club.info(), online=activity.badge(), rounds=g.get("rounds", (1, 2, 3, 4)), viewing=g.get("viewing", False), version=app.config["VERSION"], model=model,
                    charts=charts, ROLES=model.ROLES, SKILLS=model.SKILLS, POSITIONS=model.POSITIONS,
                    POSITION_GROUPS=model.POSITION_GROUPS, positions_of=helpers.positions_of)

    from . import filters
    filters.register(app)

    from . import admin, devdata, evaluation, lineup, motivation, players, reports, reset
    from .views import bp as main_bp
    for bp in (auth.bp, main_bp, players.bp, evaluation.bp, motivation.bp, devdata.bp, reports.bp, reset.bp, lineup.bp, admin.bp):
        app.register_blueprint(bp)

    @app.route("/healthz", endpoint="healthz")
    def healthz():
        return jsonify(status="ok")

    @app.errorhandler(413)
    def _413(_e):
        return ("Filen er for stor. Billeder må højst være 12 MB.", 413)

    @app.errorhandler(403)
    def _403(_e):
        return ("Ingen adgang.", 403)

    return app
