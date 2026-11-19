"""Kontolåsning uden lås-DoS.

Et simpelt «5 fejl → konto låst for alle» lader en angriber holde en kendt konto (fx admin) låst for evigt. Derfor:
- 5 forkerte forsøg fra den SAMME IP mod den samme bruger spærrer kun den IP for den bruger (den rigtige bruger er upåvirket).
- 25 forkerte forsøg i alt fra alle IP'er (fordelt angreb) låser kontoen for alle i 10 minutter.
IP-spærren pr. forbindelse (auth.throttled) kommer oven i. Rækker i login_fails ældre end vinduet tæller ikke.
"""
import time

from flask import request

PAIR_MAX = 5
USER_MAX = 25
WINDOW = 600


def client_ip():
    return request.remote_addr or "?"


def _count(db, user_id, ip=None):
    q, a = "SELECT COUNT(*) FROM login_fails WHERE user_id=? AND ts>?", [user_id, int(time.time()) - WINDOW]
    if ip is not None:
        q, a = q + " AND ip=?", a + [ip]
    return db.execute(q, a).fetchone()[0]


def is_locked(db, user):
    return user["locked_until"] > time.time() or _count(db, user["id"], client_ip()) >= PAIR_MAX


def register_fail(db, user):
    """Registrér et forkert forsøg. Returnerer True, hvis brugeren nu er låst for denne IP (eller for alle)."""
    now = int(time.time())
    db.execute("INSERT INTO login_fails(user_id,ip,ts) VALUES(?,?,?)", (user["id"], client_ip(), now))
    if _count(db, user["id"]) >= USER_MAX:
        db.execute("UPDATE users SET locked_until=? WHERE id=?", (now + WINDOW, user["id"]))
        return True
    return _count(db, user["id"], client_ip()) >= PAIR_MAX


def clear(db, user_id, all_ips=False):
    """Efter vellykket login ryddes kun denne IP's fejl; administrator/nulstilling rydder alle og låser op."""
    if all_ips:
        db.execute("DELETE FROM login_fails WHERE user_id=?", (user_id,))
        db.execute("UPDATE users SET failed_logins=0, locked_until=0 WHERE id=?", (user_id,))
    else:
        db.execute("DELETE FROM login_fails WHERE user_id=? AND ip=?", (user_id, client_ip()))
        db.execute("UPDATE users SET failed_logins=0, locked_until=0 WHERE id=?", (user_id,))
