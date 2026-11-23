"""Planlagt automatisk backup (B-13). Systemadministratoren vælger ugedage og klokkeslæt (lokal tid, TZ), hvor mange backups der gemmes,
og om planen er slået til. Baggrundstråden kalder `run_if_due` hvert par sekunder; en dags-«claim» i databasen sikrer, at kun én
worker tager backup, og at der højst tages én planlagt backup pr. dag.
Efter HVER backup opdateres `latest.db` og `latest.json` i backup-mappen, så et eksternt job (rclone/rsync/scp) altid kan hente den seneste."""
import json
import os
import re
import time
from datetime import datetime, timedelta

DAYS = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]
DEFAULT = {"enabled": False, "days": [0, 1, 2, 3, 4, 5, 6], "time": "03:30", "keep": 14}
PLAN_KEY, STATE_KEY, CLAIM_KEY = "backup_plan", "backup_state", "backup_claim"
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _get(db, key):
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def _put(db, key, value):
    db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def get_plan(db):
    plan = dict(DEFAULT)
    try:
        raw = json.loads(_get(db, PLAN_KEY) or "{}")
    except ValueError:
        raw = {}
    if isinstance(raw, dict):
        if isinstance(raw.get("enabled"), bool):
            plan["enabled"] = raw["enabled"]
        days = [d for d in raw.get("days", []) if isinstance(d, int) and 0 <= d <= 6]
        if "days" in raw:
            plan["days"] = sorted(set(days))
        if isinstance(raw.get("time"), str) and TIME_RE.match(raw["time"]):
            plan["time"] = raw["time"]
        if isinstance(raw.get("keep"), int) and 1 <= raw["keep"] <= 90:
            plan["keep"] = raw["keep"]
    return plan


def parse_form(form):
    """Returnerer (plan, fejltekst)."""
    days = sorted({int(d) for d in form.getlist("days") if d.isdigit() and 0 <= int(d) <= 6})
    t = (form.get("time") or "").strip()
    try:
        keep = int(form.get("keep", ""))
    except ValueError:
        keep = 0
    plan = {"enabled": bool(form.get("enabled")), "days": days, "time": t, "keep": keep}
    if not TIME_RE.match(t):
        return plan, "Angiv klokkeslæt som tt:mm, fx 03:30."
    if not 1 <= keep <= 90:
        return plan, "Antal gemte backups skal være mellem 1 og 90."
    if plan["enabled"] and not days:
        return plan, "Vælg mindst én ugedag."
    return plan, None


def set_plan(db, plan):
    _put(db, PLAN_KEY, json.dumps(plan))


def get_state(db):
    try:
        st = json.loads(_get(db, STATE_KEY) or "{}")
    except ValueError:
        st = {}
    return st if isinstance(st, dict) else {}


def keep_count(db):
    return get_plan(db)["keep"]


def next_run(plan, now=None):
    """Næste planlagte tidspunkt (lokal tid) eller None, hvis planen er slået fra."""
    if not plan["enabled"] or not plan["days"]:
        return None
    now = now or datetime.now()
    hh, mm = map(int, plan["time"].split(":"))
    for add in range(0, 8):
        day = (now + timedelta(days=add)).replace(hour=hh, minute=mm, second=0, microsecond=0)
        if day.weekday() in plan["days"] and day > now:
            return day
    return None


def is_due(plan, now):
    if not plan["enabled"] or now.weekday() not in plan["days"]:
        return False
    return now.strftime("%H:%M") >= plan["time"]


def run_if_due(db, db_path, backup_dir, now=None):
    """Tager backup, hvis planen siger det. Returnerer filens sti, ellers None. Kan kaldes ofte og fra flere workers samtidig."""
    from .db import audit, backup
    now = now or datetime.now()
    plan = get_plan(db)
    if not is_due(plan, now):
        return None
    today = now.strftime("%Y-%m-%d")
    cur = db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value WHERE value<>excluded.value",
                     (CLAIM_KEY, today))
    db.commit()
    if cur.rowcount != 1:                                  # allerede taget i dag (af denne eller en anden worker)
        return None
    try:
        dest = backup(db_path, backup_dir, keep=plan["keep"])
        state = {"at": now.strftime("%Y-%m-%d %H:%M"), "ok": True, "file": os.path.basename(dest), "error": ""}
        audit(db, "system", "backup_planlagt", os.path.basename(dest))
    except Exception as exc:          # noqa: BLE001 – en fejl skal vises i Administration, ikke vælte tråden
        dest = None
        state = {"at": now.strftime("%Y-%m-%d %H:%M"), "ok": False, "file": "", "error": str(exc)[:300]}
        audit(db, "system", "backup_planlagt_fejlede", state["error"])
    _put(db, STATE_KEY, json.dumps(state))
    db.commit()
    return dest


def publish_latest(dest, backup_dir):
    """Opdaterer latest.db (kopi) og latest.json (filnavn, størrelse, tidspunkt, sha256) atomisk, så et eksternt job kan hente dem."""
    import hashlib
    import shutil
    tmp = os.path.join(backup_dir, ".latest.db.tmp")
    shutil.copyfile(dest, tmp)
    os.replace(tmp, os.path.join(backup_dir, "latest.db"))
    h = hashlib.sha256()
    with open(dest, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    meta = {"file": os.path.basename(dest), "size": os.path.getsize(dest), "created": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "sha256": h.hexdigest()}
    tmp = os.path.join(backup_dir, ".latest.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f)
    os.replace(tmp, os.path.join(backup_dir, "latest.json"))
