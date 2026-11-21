"""'Husk denne enhed': 30 dages login uden adgangskode/2FA på en betroet enhed.

Design (se docs/SECURITY.md):
- Kun efter fuldt login (adgangskode + 2FA) og kun hvis brugeren aktivt sætter flueben.
- Tilfældigt 256-bit token i HttpOnly-cookie; databasen gemmer kun en nøglet hash (HMAC).
- Tokenet roteres ved hver brug; genbrug af et gammelt token (efter 60 s) tolkes som tyveri og tilbagekalder alle brugerens enheder.
- Fast udløb (REMEMBER_DAYS fra det fulde login), ikke glidende.
- Tilbagekaldes ved log ud, skift/nulstilling af adgangskode, nulstilling af 2FA og 'Glem alle enheder'.
- Administration kræver stadig frisk login med kode (trin-op), så en tabt telefon ikke giver adgang til brugerstyring/eksport.
"""
import hashlib
import hmac
import secrets
import time

from flask import current_app, g, request, session

from .db import audit

MAX_PER_USER = 10
GRACE = 60


def days():
    return int(current_app.config.get("REMEMBER_DAYS", 30))


def cookie_name():
    return "__Host-u11_rm" if current_app.config["SESSION_COOKIE_SECURE"] else "u11_rm"


def _hash(token):
    return hmac.new(current_app.config["SECRET_KEY"].encode(), token.encode(), hashlib.sha256).hexdigest()


def issue(db, user):
    """Opretter token til denne enhed. Cookien sættes i after_request."""
    if days() <= 0:
        return
    now = int(time.time())
    token = secrets.token_urlsafe(32)
    db.execute("INSERT INTO remember_tokens(user_id,token_hash,created_at,expires_at,last_used,rotated_at,ua) VALUES(?,?,?,?,?,?,?)",
               (user["id"], _hash(token), now, now + days() * 86400, now, now, (request.user_agent.string or "")[:120]))
    db.execute("DELETE FROM remember_tokens WHERE user_id=? AND id NOT IN (SELECT id FROM remember_tokens WHERE user_id=? ORDER BY id DESC LIMIT ?)",
               (user["id"], user["id"], MAX_PER_USER))
    audit(db, user["username"], "husk_enhed_sat")
    db.commit()
    g.set_remember = (token, now + days() * 86400)


def revoke_user(db, uid):
    db.execute("DELETE FROM remember_tokens WHERE user_id=?", (uid,))


def revoke_current(db):
    raw = request.cookies.get(cookie_name())
    if raw:
        h = _hash(raw)
        db.execute("DELETE FROM remember_tokens WHERE token_hash=? OR prev_hash=?", (h, h))
    g.clear_remember = True


def count(db, uid):
    return db.execute("SELECT COUNT(*) FROM remember_tokens WHERE user_id=? AND expires_at>?", (uid, int(time.time()))).fetchone()[0]


def try_restore(db):
    """Genopretter en fuld session ud fra husk-cookien. Returnerer True ved succes."""
    raw = request.cookies.get(cookie_name())
    if not raw or days() <= 0:
        return False
    now = int(time.time())
    h = _hash(raw)
    row = db.execute("SELECT * FROM remember_tokens WHERE token_hash=?", (h,)).fetchone()
    rotated_old = False
    if not row:
        row = db.execute("SELECT * FROM remember_tokens WHERE prev_hash=?", (h,)).fetchone()
        if not row:
            g.clear_remember = True
            return False
        if now - row["rotated_at"] > GRACE:                       # gammelt token genbrugt → mulig kopi/tyveri
            u = db.execute("SELECT username FROM users WHERE id=?", (row["user_id"],)).fetchone()
            revoke_user(db, row["user_id"])
            audit(db, u["username"] if u else "?", "husk_enhed_misbrug", "alle enheder tilbagekaldt")
            db.commit()
            g.clear_remember = True
            return False
        rotated_old = True                                         # to faner/forespørgsler samtidig: tillad uden ny rotation
    if row["expires_at"] <= now:
        db.execute("DELETE FROM remember_tokens WHERE id=?", (row["id"],))
        db.commit()
        g.clear_remember = True
        return False
    user = db.execute("SELECT * FROM users WHERE id=?", (row["user_id"],)).fetchone()
    from .lockout import is_locked
    if not user or not user["totp_enabled"] or is_locked(db, user):
        g.clear_remember = True
        return False
    if not rotated_old:
        new = secrets.token_urlsafe(32)
        db.execute("UPDATE remember_tokens SET token_hash=?, prev_hash=?, rotated_at=?, last_used=? WHERE id=?", (_hash(new), h, now, now, row["id"]))
        db.commit()
        g.set_remember = (new, row["expires_at"])
    from .auth import _bind
    session.clear()
    session["uid"] = user["id"]
    session["seen"] = now
    session["stage"] = "ok"
    db.execute("UPDATE users SET last_login=? WHERE id=?", (now, user["id"]))
    db.commit()
    session["auth_at"] = 0                                         # ikke 'frisk': administration kræver nyt login
    _bind(user["pw_hash"])
    return True


def apply_cookie(resp):
    secure = current_app.config["SESSION_COOKIE_SECURE"]
    if g.get("set_remember"):
        token, exp = g.set_remember
        resp.set_cookie(cookie_name(), token, max_age=max(1, exp - int(time.time())), httponly=True, secure=secure, samesite="Lax", path="/")
    elif g.get("clear_remember"):
        resp.delete_cookie(cookie_name(), path="/", secure=secure, httponly=True, samesite="Lax")
    return resp
