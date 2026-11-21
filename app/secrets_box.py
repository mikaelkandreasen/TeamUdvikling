"""Kryptering af 2FA-hemmeligheder (TOTP) i hvile.

Nøglen ligger uden for databasen: miljøvariablen TOTP_KEY, ellers filen /data/totp_key (oprettes automatisk, rettigheder 600).
En stjålet databasefil eller backup afslører dermed ikke brugernes 2FA-hemmeligheder. Gem nøglen adskilt fra backuppen
(mister du den, skal 2FA nulstilles for alle brugere – se docs/BACKUP.md). Værdier får præfikset `enc1:`; uden præfiks
læses de som klartekst (ældre data), og de krypteres ved næste opstart.
"""
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

PREFIX = "enc1:"


def load_key(data_dir, env=None):
    if env:
        return env.strip().encode()
    path = Path(data_dir) / "totp_key"
    if not path.exists():
        path.write_bytes(Fernet.generate_key())
        path.chmod(0o600)
    return path.read_bytes().strip()


def encrypt(key, value):
    if value is None or str(value).startswith(PREFIX):
        return value
    return PREFIX + Fernet(key).encrypt(str(value).encode()).decode()


def decrypt(key, value):
    if value is None or not str(value).startswith(PREFIX):
        return value                                   # ældre klartekst
    try:
        return Fernet(key).decrypt(str(value)[len(PREFIX):].encode()).decode()
    except InvalidToken:
        return None                                    # forkert nøgle: 2FA-kode kan ikke verificeres → login afvises


def encrypt_all(db, key):
    """Krypterer eksisterende klartekst-hemmeligheder. Idempotent."""
    n = 0
    for r in db.execute("SELECT id, totp_secret FROM users WHERE totp_secret IS NOT NULL AND totp_secret<>'' AND totp_secret NOT LIKE ?", (PREFIX + "%",)).fetchall():
        db.execute("UPDATE users SET totp_secret=? WHERE id=?", (encrypt(key, r["totp_secret"]), r["id"]))
        n += 1
    db.commit()
    return n
