"""TOTP (RFC 6238) uden eksterne afhængigheder – kompatibel med Google/Microsoft Authenticator, Authy, 1Password m.fl."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret):
    s = secret.replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def hotp(secret, counter, digits=6):
    mac = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def step_at(t=None, period=30):
    return int((time.time() if t is None else t) // period)


def totp(secret, t=None, digits=6, period=30):
    return hotp(secret, step_at(t, period), digits)


def verify(secret, code, last_step=0, t=None, window=1):
    """Returnerer det matchende tidstrin (int) eller None. Et tidstrin kan kun bruges én gang (replay-beskyttelse)."""
    code = (code or "").strip().replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return None
    now = step_at(t)
    for step in range(now - window, now + window + 1):
        if step > last_step and hmac.compare_digest(hotp(secret, step), code):
            return step
    return None


def otpauth_uri(secret, username, issuer="U11 Udvikling"):
    return (f"otpauth://totp/{quote(issuer)}:{quote(username)}?secret={secret}"
            f"&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30")
