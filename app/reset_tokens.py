"""Engangstokens til nulstilling af adgangskode/2FA via e-mail. Kun HMAC-hash gemmes; 60 min levetid; maks. 3 pr. time pr. bruger."""
import hashlib
import hmac
import secrets
import time

from flask import current_app

TTL = 3600
MAX_PER_HOUR = 3


def _h(token):
    return hmac.new(current_app.config["SECRET_KEY"].encode(), (token or "").encode(), hashlib.sha256).hexdigest()


def issue(db, user_id, purpose, requested_by):
    """Opretter et nyt token (gamle ubrugte for samme formål ugyldiggøres). None hvis grænsen pr. time er nået."""
    now = int(time.time())
    n = db.execute("SELECT COUNT(*) FROM reset_tokens WHERE user_id=? AND created_at>?", (user_id, now - 3600)).fetchone()[0]
    if n >= MAX_PER_HOUR:
        return None
    db.execute("UPDATE reset_tokens SET used_at=? WHERE user_id=? AND purpose=? AND used_at IS NULL", (now, user_id, purpose))
    token = secrets.token_urlsafe(32)
    db.execute("INSERT INTO reset_tokens(user_id,purpose,token_hash,created_at,expires_at,requested_by) VALUES(?,?,?,?,?,?)",
               (user_id, purpose, _h(token), now, now + TTL, requested_by))
    return token


def lookup(db, token):
    """Gyldigt (ubrugt, ikke udløbet) token eller None. Forbruger ikke tokenet – mailscannere kan åbne linket uden skade."""
    if not token or len(token) > 100:
        return None
    return db.execute("SELECT * FROM reset_tokens WHERE token_hash=? AND used_at IS NULL AND expires_at>?",
                      (_h(token), int(time.time()))).fetchone()


def finish(db, row):
    """Forbrug tokenet og ugyldiggør alle andre ubrugte tokens for brugeren."""
    db.execute("UPDATE reset_tokens SET used_at=? WHERE user_id=? AND used_at IS NULL", (int(time.time()), row["user_id"]))


def discard(db, token):
    db.execute("DELETE FROM reset_tokens WHERE token_hash=?", (_h(token),))


def revoke_user(db, user_id):
    """Ugyldiggør afventende links (adgangskodeskift, 2FA-nulstilling, ny e-mailadresse)."""
    db.execute("UPDATE reset_tokens SET used_at=? WHERE user_id=? AND used_at IS NULL", (int(time.time()), user_id))
