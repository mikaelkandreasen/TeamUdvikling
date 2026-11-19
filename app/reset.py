"""Nulstilling af adgangskode/2FA via e-mail. Kun administrator kan udløse en mail (efter bekræftelse med egen 2FA-kode);
den offentlige side /nulstil/<token> bruger engangslinket. Selvbetjent «glemt adgangskode» findes bevidst ikke."""
import time

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import lockout, mailer, remember, reset_tokens
from .auth import _bind, _fail, _too_many, check_password_policy, record_fail, throttled
from .db import audit, club_get, get_db

bp = Blueprint("reset", __name__)

TEXT = {
    "password": ("nulstille din adgangskode",
                 "Åbn linket og vælg en ny adgangskode. Du skal stadig bruge din 2FA-kode, når du logger ind."),
    "totp": ("nulstille din to-faktor-login (2FA)",
             "Åbn linket, bekræft med din adgangskode og scan en ny QR-kode i din autentificeringsapp."),
}


def send_reset(db, user, purpose, admin_name):
    """Sender nulstillingsmail. Returnerer (ok, besked). Kalderen har allerede verificeret administratorens 2FA-kode."""
    if not user["email"]:
        return False, "Brugeren har ingen e-mailadresse."
    todo = mailer.missing()
    if todo:
        return False, f"E-mail er ikke sat op: mangler {todo}."
    token = reset_tokens.issue(db, user["id"], purpose, admin_name)
    if token is None:
        return False, "Der er sendt for mange nulstillinger til brugeren den seneste time. Prøv igen senere."
    what, how = TEXT[purpose]
    info = club_get(db)
    club = info["name"] or info["app_name"]
    body = (f"Hej {user['display_name']},\n\n"
            f"En administrator har godkendt, at du må {what} i {club}.\n\n"
            f"{how}\n\n{mailer.public_url()}/nulstil/{token}\n\n"
            f"Linket virker i {reset_tokens.TTL // 60} minutter og kan kun bruges én gang.\n"
            "Har du ikke bedt om det, så ignorér mailen og fortæl din administrator det.\n")
    try:
        mailer.send(user["email"], f"{club}: nulstilling", body)
    except Exception as exc:     # noqa: BLE001 – SMTP kan fejle på mange måder; tokenet må ikke blive liggende
        reset_tokens.discard(db, token)
        db.commit()
        current_app.logger.warning("Nulstillingsmail kunne ikke sendes (%s)", type(exc).__name__)
        return False, f"E-mailen kunne ikke sendes ({type(exc).__name__}). Tjek SMTP-indstillingerne."
    return True, "E-mail sendt. Linket virker i 60 minutter."


def _invalid():
    return render_template("reset_invalid.html"), 400


@bp.route("/nulstil/<token>", methods=["GET", "POST"])
def link(token):
    db = get_db()
    if throttled(db):
        return _too_many()
    row = reset_tokens.lookup(db, token)
    if not row:
        record_fail(db)
        return _invalid()
    user = db.execute("SELECT * FROM users WHERE id=?", (row["user_id"],)).fetchone()
    tpl = "reset_password.html" if row["purpose"] == "password" else "reset_2fa.html"
    if request.method == "GET":
        return render_template(tpl, token=token)
    if row["purpose"] == "password":
        new = request.form.get("new", "")
        problem = ("De to adgangskoder er ikke ens." if new != request.form.get("new2", "")
                   else check_password_policy(new, user["username"]))
        if problem:
            flash(problem, "error")
            return render_template(tpl, token=token)
        db.execute("UPDATE users SET pw_hash=?, must_change_pw=0 WHERE id=?", (generate_password_hash(new), user["id"]))
        lockout.clear(db, user["id"], all_ips=True)
        remember.revoke_user(db, user["id"])
        reset_tokens.finish(db, row)
        audit(db, user["username"], "nulstil_adgangskode_mail")
        db.commit()
        session.clear()
        flash("Adgangskoden er ændret. Log ind med din nye adgangskode og din 2FA-kode.", "ok")
        return redirect(url_for("auth.login"))
    # 2FA: e-mail alene må aldrig kunne omgå 2FA – den nuværende adgangskode skal også kendes.
    locked = lockout.is_locked(db, user)
    good = check_password_hash(user["pw_hash"], request.form.get("password", "")[:1024])
    if locked or not good:
        if not locked:
            _fail(db, user)
        record_fail(db)
        flash("Forkert adgangskode, eller kontoen er midlertidigt låst.", "error")
        return render_template(tpl, token=token)
    db.execute("UPDATE users SET totp_secret=NULL, totp_enabled=0, last_totp_step=0 WHERE id=?", (user["id"],))
    lockout.clear(db, user["id"], all_ips=True)
    db.execute("DELETE FROM recovery_codes WHERE user_id=?", (user["id"],))
    remember.revoke_user(db, user["id"])
    reset_tokens.finish(db, row)
    audit(db, user["username"], "nulstil_2fa_mail")
    db.commit()
    session.clear()
    session["uid"] = user["id"]
    session["seen"] = int(time.time())
    _bind(user["pw_hash"])
    session["stage"] = "needs_setup"
    return redirect(url_for("auth.twofa_setup"))
