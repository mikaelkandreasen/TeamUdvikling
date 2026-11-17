"""U11 Udvikling – Flask-app til spillerudvikling (DBU-roller x nøglefærdigheder)."""
import hmac
import os
import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, abort, g, jsonify, request, session

from . import auth, charts, db, model, teams

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

    app.teardown_appcontext(db.close_db)

    @app.before_request
    def _before():
        session.permanent = True
        auth.load_user()
        teams.resolve(db.get_db(), g.get("user"))
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
            if not sent or not hmac.compare_digest(sent, session.get("csrf", "")):
                abort(400, "Ugyldig eller udløbet formular (CSRF). Gå tilbage, genindlæs siden og prøv igen.")
        return auth.gate()

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Content-Security-Policy",
                                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                "script-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'")
        if request.endpoint != "static":
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.context_processor
    def _ctx():
        def csrf_token():
            if "csrf" not in session:
                session["csrf"] = secrets.token_urlsafe(32)
            return session["csrf"]
        return dict(csrf_token=csrf_token, user=g.get("user"), team=g.get("team"), teams=g.get("teams", []), version=app.config["VERSION"], model=model,
                    charts=charts, ROLES=model.ROLES, SKILLS=model.SKILLS, POSITIONS=model.POSITIONS)

    from . import filters
    filters.register(app)

    from . import admin, devdata, evaluation, motivation, players, reports
    from .views import bp as main_bp
    for bp in (auth.bp, main_bp, players.bp, evaluation.bp, motivation.bp, devdata.bp, reports.bp, admin.bp):
        app.register_blueprint(bp)

    @app.route("/healthz", endpoint="healthz")
    def healthz():
        return jsonify(status="ok", version=app.config["VERSION"])

    @app.errorhandler(403)
    def _403(_e):
        return ("Ingen adgang.", 403)

    return app
