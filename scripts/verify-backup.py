#!/usr/bin/env python3
"""Kontrollér en backupfil (kun læsning): integritet, fremmednøgler, skemaversion og antal rækker.
Brug:  python3 scripts/verify-backup.py u11-20261121-030000.db
Kør den også på en kopi, der er hentet hjem fra off-site-lageret – en backup er først rigtig, når den er gendannet og kontrolleret."""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app.db import verify_backup  # noqa: E402

if len(sys.argv) != 2:
    sys.exit(__doc__)
ok, msgs = verify_backup(sys.argv[1])
if not ok:
    print("FEJL: " + "; ".join(msgs))
    sys.exit(1)
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
print("OK  skema v%s" % con.execute("PRAGMA user_version").fetchone()[0])
for t in ("clubs", "teams", "users", "players", "evaluations"):
    print(f"    {t:12} {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
