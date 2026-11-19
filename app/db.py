"""SQLite-lag. Databasen oprettes tom – der indlæses aldrig spillerdata automatisk."""
import os
import sqlite3
import time

from flask import current_app, g

from . import model

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, display_name TEXT NOT NULL,
  pw_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'trainer', totp_secret TEXT,
  totp_enabled INTEGER NOT NULL DEFAULT 0, last_totp_step INTEGER NOT NULL DEFAULT 0,
  failed_logins INTEGER NOT NULL DEFAULT 0, locked_until INTEGER NOT NULL DEFAULT 0,
  must_change_pw INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, email TEXT);
CREATE TABLE IF NOT EXISTS recovery_codes(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code_hash TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS teams(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, season TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS user_teams(
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE, PRIMARY KEY(user_id, team_id));
CREATE TABLE IF NOT EXISTS players(
  id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  name TEXT NOT NULL, birth_date TEXT, shirt_no TEXT, position TEXT, position2 TEXT,
  foot TEXT, start_date TEXT, focus1 TEXT, focus2 TEXT, notes TEXT, active INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS players_team ON players(team_id);
CREATE TABLE IF NOT EXISTS evaluations(
  round INTEGER NOT NULL, player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  trainer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, crit INTEGER NOT NULL,
  score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 5), PRIMARY KEY(round, player_id, trainer_id, crit));
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS motivation_categories(
  team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE, cat INTEGER NOT NULL, title TEXT NOT NULL, PRIMARY KEY(team_id, cat));
CREATE TABLE IF NOT EXISTS motivation_questions(
  team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE, qidx INTEGER NOT NULL, cat INTEGER NOT NULL,
  text TEXT NOT NULL DEFAULT '', PRIMARY KEY(team_id, qidx));
CREATE TABLE IF NOT EXISTS motivation_answers(
  player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE, qidx INTEGER NOT NULL,
  score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 5), PRIMARY KEY(player_id, qidx));
CREATE TABLE IF NOT EXISTS devdata(
  player_id INTEGER PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
  trainings INTEGER, matches INTEGER, t1 INTEGER, t2 INTEGER, t3 INTEGER,
  m1 INTEGER, m2 INTEGER, m3 INTEGER, m4 INTEGER,
  tiltag TEXT, eget_maal TEXT, followup TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, user TEXT, action TEXT NOT NULL, detail TEXT);
CREATE TABLE IF NOT EXISTS backlog_items(
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT, priority INTEGER NOT NULL DEFAULT 2,
  status TEXT NOT NULL DEFAULT 'Ny', position INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS remember_tokens(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE, prev_hash TEXT, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
  last_used INTEGER NOT NULL, rotated_at INTEGER NOT NULL, ua TEXT);
CREATE INDEX IF NOT EXISTS ix_remember_prev ON remember_tokens(prev_hash);
CREATE TABLE IF NOT EXISTS reset_tokens(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  purpose TEXT NOT NULL CHECK(purpose IN ('password','totp')), token_hash TEXT NOT NULL UNIQUE,
  created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, used_at INTEGER, requested_by TEXT);
CREATE INDEX IF NOT EXISTS ix_reset_user ON reset_tokens(user_id, created_at);
CREATE TABLE IF NOT EXISTS login_attempts(ip TEXT NOT NULL, ts INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_login_attempts ON login_attempts(ip, ts);
"""


def connect(path):
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


SCHEMA_VERSION = 4   # v4: users.email + reset_tokens (migration: ADD COLUMN, idempotent); v3: remember_tokens; v2: backlog_items (oprettes med IF NOT EXISTS – ingen datamigration nødvendig)  # øg ved skemaændringer og tilføj migration i MIGRATIONS


def _migrate(con):
    """Idempotente skemaændringer på eksisterende databaser. Sletter aldrig data."""
    cols = {r["name"] for r in con.execute("PRAGMA table_info(users)")}
    if "email" not in cols:                                   # v4
        con.execute("ALTER TABLE users ADD COLUMN email TEXT")


def init_db(path):
    con = connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    _migrate(con)
    ver = con.execute("PRAGMA user_version").fetchone()[0]
    if ver < SCHEMA_VERSION:
        con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    con.commit()
    con.close()


def seed_team(db, team_id):
    """Skabelon-spørgsmål til et nyt hold (ingen spillerdata)."""
    qidx = 0
    for cat, (title, questions) in enumerate(model.DEFAULT_CATEGORIES):
        db.execute("INSERT OR IGNORE INTO motivation_categories(team_id,cat,title) VALUES(?,?,?)", (team_id, cat, title))
        for k in range(model.CAT_SIZES[cat]):
            text = questions[k] if k < len(questions) else ""
            db.execute("INSERT OR IGNORE INTO motivation_questions(team_id,qidx,cat,text) VALUES(?,?,?,?)", (team_id, qidx, cat, text))
            qidx += 1


def create_team(db, name, season=""):
    cur = db.execute("INSERT INTO teams(name,season,created_at) VALUES(?,?,datetime('now'))", (name, season or None))
    seed_team(db, cur.lastrowid)
    return cur.lastrowid


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def _k(team_id, key):
    return f"t{team_id}:{key}"


def get_setting(db, team_id, key, default=""):
    """Indstillinger er pr. hold (nøgle = t<hold-id>:<navn>)."""
    row = db.execute("SELECT value FROM settings WHERE key=?", (_k(team_id, key),)).fetchone()
    return row["value"] if row and row["value"] is not None else default


def set_setting(db, team_id, key, value):
    db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (_k(team_id, key), value))


def audit(db, user, action, detail=""):
    db.execute("INSERT INTO audit_log(ts,user,action,detail) VALUES(datetime('now','localtime'),?,?,?)",
               (user, action, detail))


AUDIT_RETENTION_DAYS = 365


def purge_old(db):
    """Dataminimering: audit-log slettes efter 12 måneder; gamle loginforsøg ryddes."""
    db.execute("DELETE FROM audit_log WHERE ts < datetime('now','localtime',?)", (f"-{AUDIT_RETENTION_DAYS} days",))
    db.execute("DELETE FROM login_attempts WHERE ts < ?", (int(time.time()) - 3600,))
    db.execute("DELETE FROM reset_tokens WHERE expires_at < ?", (int(time.time()) - 86400,))
    db.commit()


def backup(db_path, backup_dir, keep=14):
    """Konsistent kopi af databasen via SQLite's backup-API. Beholder de seneste `keep` filer."""
    os.makedirs(backup_dir, exist_ok=True)
    dest = os.path.join(backup_dir, time.strftime("u11-%Y%m%d-%H%M%S.db"))
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(dest)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    files = sorted(f for f in os.listdir(backup_dir) if f.startswith("u11-") and f.endswith(".db"))
    for old in files[:-keep]:
        os.remove(os.path.join(backup_dir, old))
    return dest


def backup_if_due(db_path, backup_dir, hours=24):
    os.makedirs(backup_dir, exist_ok=True)
    files = sorted(f for f in os.listdir(backup_dir) if f.startswith("u11-") and f.endswith(".db"))
    if files:
        age = time.time() - os.path.getmtime(os.path.join(backup_dir, files[-1]))
        if age < hours * 3600:
            return None
    return backup(db_path, backup_dir)


# ------------------------------------------------------------------ klubprofil (gælder alle hold)
CLUB_FIELDS = ("name", "address", "email", "phone", "website", "footer", "color")


def club_get(db):
    out = {f: "" for f in CLUB_FIELDS + ("logo_mime", "logo_v")}
    for row in db.execute("SELECT key, value FROM settings WHERE key LIKE 'club:%'"):
        k = row["key"][5:]
        if k in out:
            out[k] = row["value"] or ""
    return out


def club_set(db, key, value):
    db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (f"club:{key}", value))
