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
  id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE, season TEXT, created_at TEXT NOT NULL,
  club_id INTEGER REFERENCES clubs(id) ON DELETE CASCADE, UNIQUE(club_id, name));
CREATE TABLE IF NOT EXISTS user_teams(
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE, PRIMARY KEY(user_id, team_id));
CREATE TABLE IF NOT EXISTS players(
  id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  name TEXT NOT NULL, birth_date TEXT, shirt_no TEXT, position TEXT, position2 TEXT, position3 TEXT, position4 TEXT,
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
CREATE TABLE IF NOT EXISTS player_photos(
  player_id INTEGER PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
  full BLOB NOT NULL, thumb BLOB NOT NULL, consent_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS team_mascot_img(
  team_id INTEGER PRIMARY KEY REFERENCES teams(id) ON DELETE CASCADE, img BLOB NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY, club_id INTEGER NOT NULL, team_id INTEGER REFERENCES teams(id) ON DELETE CASCADE,
  sender_id INTEGER REFERENCES users(id) ON DELETE SET NULL, sender_name TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL,
  to_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, reply_to INTEGER);
CREATE INDEX IF NOT EXISTS ix_messages_club ON messages(club_id, team_id, id);
CREATE TABLE IF NOT EXISTS message_reads(
  message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  read_at TEXT NOT NULL, PRIMARY KEY(message_id, user_id));
CREATE TABLE IF NOT EXISTS conversations(
  id INTEGER PRIMARY KEY, player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE, held_on TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '', agreements TEXT NOT NULL DEFAULT '', homework TEXT NOT NULL DEFAULT '',
  trainer_id INTEGER REFERENCES users(id) ON DELETE SET NULL, trainer_name TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_conversations ON conversations(player_id, held_on);
CREATE TABLE IF NOT EXISTS motivation_log(
  player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE, qidx INTEGER NOT NULL, score INTEGER NOT NULL, taken_on TEXT NOT NULL,
  PRIMARY KEY(player_id, qidx, taken_on));
CREATE TRIGGER IF NOT EXISTS trg_motlog_ins AFTER INSERT ON motivation_answers BEGIN
  INSERT OR REPLACE INTO motivation_log(player_id,qidx,score,taken_on) VALUES(NEW.player_id,NEW.qidx,NEW.score,date('now','localtime')); END;
CREATE TRIGGER IF NOT EXISTS trg_motlog_upd AFTER UPDATE OF score ON motivation_answers BEGIN
  INSERT OR REPLACE INTO motivation_log(player_id,qidx,score,taken_on) VALUES(NEW.player_id,NEW.qidx,NEW.score,date('now','localtime')); END;
CREATE TABLE IF NOT EXISTS lineups(
  id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  name TEXT NOT NULL, game_type TEXT NOT NULL, formation TEXT NOT NULL, is_ideal INTEGER NOT NULL DEFAULT 0,
  created_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS lineups_team ON lineups(team_id, game_type);
CREATE TABLE IF NOT EXISTS lineup_slots(
  lineup_id INTEGER NOT NULL REFERENCES lineups(id) ON DELETE CASCADE, slot INTEGER NOT NULL,
  player_id INTEGER REFERENCES players(id) ON DELETE SET NULL, PRIMARY KEY(lineup_id, slot), UNIQUE(lineup_id, player_id));
CREATE TABLE IF NOT EXISTS login_fails(user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, ip TEXT NOT NULL, ts INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_login_fails ON login_fails(user_id, ip, ts);
CREATE TABLE IF NOT EXISTS revoked_sessions(sid_hash TEXT PRIMARY KEY, expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS presence(user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, last_seen INTEGER NOT NULL, team_id INTEGER);
CREATE TABLE IF NOT EXISTS activity(user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, slot INTEGER NOT NULL, team_id INTEGER, PRIMARY KEY(user_id, slot));
CREATE INDEX IF NOT EXISTS ix_activity_slot ON activity(slot);
CREATE TABLE IF NOT EXISTS clubs(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, app_name TEXT, address TEXT, email TEXT, phone TEXT, website TEXT, footer TEXT,
  color TEXT, logo BLOB, logo_mime TEXT, logo_v TEXT, created_at TEXT NOT NULL, motto TEXT);
CREATE TABLE IF NOT EXISTS invitations(
  id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, email TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'trainer',
  club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE, team_ids TEXT NOT NULL DEFAULT '',
  created_by TEXT NOT NULL, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, used_at INTEGER, revoked INTEGER NOT NULL DEFAULT 0,
  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL);
CREATE INDEX IF NOT EXISTS ix_invitations_club ON invitations(club_id, created_at);
CREATE TABLE IF NOT EXISTS level_ratings(
  round INTEGER NOT NULL, player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  trainer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  level TEXT NOT NULL, PRIMARY KEY(round, player_id, trainer_id));
CREATE TABLE IF NOT EXISTS eval_history(
  id INTEGER PRIMARY KEY, player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE, team_name TEXT NOT NULL, moved_at TEXT NOT NULL,
  round_no INTEGER NOT NULL, round_label TEXT NOT NULL, round_date TEXT, trainer_name TEXT NOT NULL, kind TEXT NOT NULL, k TEXT NOT NULL, v TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_eval_history ON eval_history(player_id);
CREATE TABLE IF NOT EXISTS dbu_checks(
  round INTEGER NOT NULL, player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  trainer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, item TEXT NOT NULL, PRIMARY KEY(round, player_id, trainer_id, item));
CREATE TABLE IF NOT EXISTS user_profiles(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK(role IN ('trainer','clubadmin','admin')), club_id INTEGER REFERENCES clubs(id) ON DELETE CASCADE,
  UNIQUE(user_id, role, club_id));
CREATE TABLE IF NOT EXISTS security_events(
  id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, kind TEXT NOT NULL, detail TEXT, ip TEXT);
CREATE INDEX IF NOT EXISTS ix_security_events ON security_events(ts);
CREATE TABLE IF NOT EXISTS player_links(
  id INTEGER PRIMARY KEY, player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
  used_at INTEGER, revoked INTEGER NOT NULL DEFAULT 0, created_by TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_player_links ON player_links(player_id);
CREATE TABLE IF NOT EXISTS wellbeing(
  player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE, day TEXT NOT NULL,
  t1 INTEGER, t2 INTEGER, t3 INTEGER, PRIMARY KEY(player_id, day));
CREATE TABLE IF NOT EXISTS att_events(
  id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK(kind IN ('training','match')), day TEXT NOT NULL, note TEXT, created_by TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_att_events ON att_events(team_id, day);
CREATE TABLE IF NOT EXISTS att_marks(
  event_id INTEGER NOT NULL REFERENCES att_events(id) ON DELETE CASCADE,
  player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE, PRIMARY KEY(event_id, player_id));
CREATE TABLE IF NOT EXISTS team_heads(
  team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY(team_id, user_id));
CREATE TABLE IF NOT EXISTS team_notes(
  id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE, user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  author TEXT NOT NULL, created_at TEXT NOT NULL, body TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_team_notes ON team_notes(team_id, created_at);
CREATE TABLE IF NOT EXISTS mascot_log(
  id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE, taken_on TEXT NOT NULL, returned_on TEXT,
  reason TEXT NOT NULL, note TEXT, created_by TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_mascot_team ON mascot_log(team_id, taken_on);
CREATE TABLE IF NOT EXISTS login_attempts(ip TEXT NOT NULL, ts INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_login_attempts ON login_attempts(ip, ts);
"""


def connect(path):
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


SCHEMA_VERSION = 20   # v20: messages.to_user_id/reply_to (svar), conversations (forældresamtaler), motivation_log + triggers (motivation over tid; IF NOT EXISTS/ADD COLUMN); v19: messages + message_reads (indbakke: klub- og holdbeskeder; IF NOT EXISTS); v18: clubs.motto (klubmotto; ADD COLUMN, idempotent); v17: team_mascot_img (maskotbillede til forældrerapporten; IF NOT EXISTS); v16: eval_history (evalueringer følger spilleren ved holdskifte), users.stopped_at (stoppede trænere beholder deres evalueringer), runde-åbning (30 dage); v15: team_notes.title/note_date/updated_at/updated_by (delte holdnoter i wiki-stil; ADD COLUMN, idempotent); v14: dbu_checks (trænerens afkrydsning af DBU-niveau-udsagn pr. spiller og runde; IF NOT EXISTS); v13: user_profiles (ekstra profiler pr. bruger: træner/klubadministrator/systemadministrator med klub; IF NOT EXISTS), level_ratings.level (A+/A/B/C/D/Nystartet i stedet for 1-5; gamle rækker omsat og tabellen genopbygget); v12: niveauer følger DBU (A, B, C, D): A+→A og Ny→D (idempotent); v11: level_ratings (trænernes samlede niveauvurdering pr. spiller og runde; IF NOT EXISTS); v10: players.deactivated_at (opbevaringsfrist), users.readonly + invitations.as_readonly (assistent = træner med læseadgang), teams.archived (sæsonskifte), att_events + att_marks (fremmøde pr. træning/kamp), wellbeing (trivsel over tid), player_links (spillerlink til motivationsskema), security_events (blokeringslog, 30 dage) – alle IF NOT EXISTS; v9: players.level, teams.slogan/mascot_name, team_heads (chef-trænere), invitations.as_head, users.last_login, team_notes, mascot_log; v8: clubs, invitations, users.club_id, teams.club_id (migration flytter klubprofil/logo til clubs); v7: v7: presence + activity (IF NOT EXISTS); v6: v6: players.position3/4, player_photos, lineups, lineup_slots (ADD COLUMN/IF NOT EXISTS, idempotent); v5: login_fails + revoked_sessions (IF NOT EXISTS); v4: users.email + reset_tokens (migration: ADD COLUMN, idempotent); v3: remember_tokens; v2: backlog_items (oprettes med IF NOT EXISTS – ingen datamigration nødvendig)  # øg ved skemaændringer og tilføj migration i MIGRATIONS


def _migrate(con):
    """Idempotente skemaændringer på eksisterende databaser. Sletter aldrig data."""
    cols = {r["name"] for r in con.execute("PRAGMA table_info(users)")}
    if "email" not in cols:                                   # v4
        con.execute("ALTER TABLE users ADD COLUMN email TEXT")
    pcols = {r["name"] for r in con.execute("PRAGMA table_info(players)")}
    for c in ("position3", "position4"):                      # v6
        if c not in pcols:
            con.execute(f"ALTER TABLE players ADD COLUMN {c} TEXT")


def _migrate_clubs(con):
    """v8: klubprofilen flyttes fra settings ('club:*') og logofilen til tabellen clubs; eksisterende hold/brugere får klub 1."""
    ucols = {r["name"] for r in con.execute("PRAGMA table_info(users)")}
    if "club_id" not in ucols:
        con.execute("ALTER TABLE users ADD COLUMN club_id INTEGER REFERENCES clubs(id)")
    if con.execute("SELECT COUNT(*) FROM clubs").fetchone()[0] == 0:
        legacy = {r["key"][5:]: r["value"] or "" for r in con.execute("SELECT key, value FROM settings WHERE key LIKE 'club:%'")}
        logo = None
        try:
            main_file = next(r["file"] for r in con.execute("PRAGMA database_list") if r["name"] == "main")
            with open(os.path.join(os.path.dirname(main_file), "branding", "logo.bin"), "rb") as fh:
                logo = fh.read()
        except (StopIteration, OSError):
            pass
        con.execute("INSERT INTO clubs(id,name,app_name,address,email,phone,website,footer,color,logo,logo_mime,logo_v,created_at) "
                    "VALUES(1,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
                    (legacy.get("name") or "", legacy.get("app_name") or "", legacy.get("address", ""), legacy.get("email", ""),
                     legacy.get("phone", ""), legacy.get("website", ""), legacy.get("footer", ""), legacy.get("color", ""),
                     logo, legacy.get("logo_mime", "") if logo else "", legacy.get("logo_v", "") if logo else ""))
        con.execute("DELETE FROM settings WHERE key LIKE 'club:%'")
    first = con.execute("SELECT MIN(id) FROM clubs").fetchone()[0]
    if "club_id" not in {r["name"] for r in con.execute("PRAGMA table_info(teams)")}:
        # Holdnavne skal være unikke pr. klub (før: globalt). SQLite kan ikke fjerne UNIQUE → genopbyg tabellen (officiel 12-trins metode).
        con.commit()
        con.execute("PRAGMA foreign_keys=OFF")
        con.executescript("""BEGIN;
            CREATE TABLE teams_new(id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE, season TEXT, created_at TEXT NOT NULL,
              club_id INTEGER REFERENCES clubs(id) ON DELETE CASCADE, UNIQUE(club_id, name));
            INSERT INTO teams_new(id,name,season,created_at,club_id) SELECT id,name,season,created_at,%d FROM teams;
            DROP TABLE teams;
            ALTER TABLE teams_new RENAME TO teams;
            COMMIT;""" % first)
        con.execute("PRAGMA foreign_keys=ON")
        assert not con.execute("PRAGMA foreign_key_check").fetchall()
    con.execute("UPDATE teams SET club_id=? WHERE club_id IS NULL", (first,))
    con.execute("UPDATE users SET club_id=? WHERE club_id IS NULL AND role<>'admin'", (first,))


def _migrate_team_features(con):
    """v9: spillerniveau, slogan, mascot og chef-træner (ADD COLUMN, idempotent)."""
    pcols = {r["name"] for r in con.execute("PRAGMA table_info(players)")}
    if "level" not in pcols:
        con.execute("ALTER TABLE players ADD COLUMN level TEXT")
    if "deactivated_at" not in pcols:
        con.execute("ALTER TABLE players ADD COLUMN deactivated_at TEXT")
        con.execute("UPDATE players SET deactivated_at=date('now','localtime') WHERE active=0")      # eksisterende inaktive: fristen starter nu
    tcols = {r["name"] for r in con.execute("PRAGMA table_info(teams)")}
    for col, ddl in (("slogan", "TEXT"), ("mascot_name", "TEXT"), ("archived", "INTEGER NOT NULL DEFAULT 0")):
        if col not in tcols:
            con.execute(f"ALTER TABLE teams ADD COLUMN {col} {ddl}")
    ucols = {r["name"] for r in con.execute("PRAGMA table_info(users)")}
    if "readonly" not in ucols:
        con.execute("ALTER TABLE users ADD COLUMN readonly INTEGER NOT NULL DEFAULT 0")
    if "last_login" not in ucols:
        con.execute("ALTER TABLE users ADD COLUMN last_login INTEGER")
    icols = {r["name"] for r in con.execute("PRAGMA table_info(invitations)")}
    if "as_readonly" not in icols:
        con.execute("ALTER TABLE invitations ADD COLUMN as_readonly INTEGER NOT NULL DEFAULT 0")
    if "as_head" not in icols:
        con.execute("ALTER TABLE invitations ADD COLUMN as_head INTEGER NOT NULL DEFAULT 0")


def _migrate_v20(con):
    """v20: messages.to_user_id/reply_to (ADD COLUMN) + udgangspunkt for motivation over tid (idempotent)."""
    cols = {r["name"] for r in con.execute("PRAGMA table_info(messages)")}
    for c, d in (("to_user_id", "INTEGER REFERENCES users(id) ON DELETE CASCADE"), ("reply_to", "INTEGER")):
        if c not in cols:
            con.execute(f"ALTER TABLE messages ADD COLUMN {c} {d}")
    con.execute("INSERT OR IGNORE INTO motivation_log(player_id,qidx,score,taken_on) SELECT player_id,qidx,score,date('now','localtime') FROM motivation_answers")


def _migrate_club_motto(con):
    """v18: clubs.motto (klubbens motto; idempotent)."""
    if "motto" not in {r["name"] for r in con.execute("PRAGMA table_info(clubs)")}:
        con.execute("ALTER TABLE clubs ADD COLUMN motto TEXT")


def _migrate_stopped_users(con):
    """v16: users.stopped_at (idempotent)."""
    if "stopped_at" not in {r["name"] for r in con.execute("PRAGMA table_info(users)")}:
        con.execute("ALTER TABLE users ADD COLUMN stopped_at INTEGER")


def _migrate_round_opening(con):
    """v16: runder lukkes 30 dage efter første indtastning. Eksisterende runder med data får åbningsdato = i dag (idempotent)."""
    from datetime import date
    for r in con.execute("SELECT DISTINCT p.team_id AS t, e.round AS r FROM evaluations e JOIN players p ON p.id=e.player_id").fetchall():
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (f"t{r['t']}:round_opened_{r['r']}", date.today().isoformat()))


def _migrate_team_notes(con):
    """v15: holdnoter får titel, dato, og «sidst redigeret» (idempotent)."""
    cols = {r["name"] for r in con.execute("PRAGMA table_info(team_notes)")}
    for name, ddl in (("title", "TEXT NOT NULL DEFAULT ''"), ("note_date", "TEXT"), ("updated_at", "TEXT"), ("updated_by", "TEXT")):
        if name not in cols:
            con.execute(f"ALTER TABLE team_notes ADD COLUMN {name} {ddl}")
    con.execute("UPDATE team_notes SET note_date=substr(created_at,1,10) WHERE note_date IS NULL OR note_date=''")


def _migrate_dbu_levels(con):
    """v12/v13: «Ny» hedder nu «Nystartet» (A+ bevares). Trænernes niveauvurdering gemmes som niveau i stedet for tal 1-5
    (5→A, 4→B, 3→C, 2→D, 1→Nystartet); tabellen genopbygges, gamle rækker omsættes (idempotent)."""
    con.execute("UPDATE players SET level='Nystartet' WHERE level IN ('Ny')")
    cols = {r["name"] for r in con.execute("PRAGMA table_info(level_ratings)")}
    if "level" not in cols:
        con.execute("ALTER TABLE level_ratings RENAME TO level_ratings_old")
        con.execute("CREATE TABLE level_ratings(round INTEGER NOT NULL, player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE, "
                    "trainer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, level TEXT NOT NULL, PRIMARY KEY(round, player_id, trainer_id))")
        con.execute("INSERT INTO level_ratings(round,player_id,trainer_id,level) SELECT round,player_id,trainer_id,"
                    "CASE score WHEN 5 THEN 'A' WHEN 4 THEN 'B' WHEN 3 THEN 'C' WHEN 2 THEN 'D' ELSE 'Nystartet' END FROM level_ratings_old")
        con.execute("DROP TABLE level_ratings_old")


def init_db(path):
    con = connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    _migrate(con)
    _migrate_clubs(con)
    _migrate_team_features(con)
    _migrate_dbu_levels(con)
    _migrate_team_notes(con)
    _migrate_round_opening(con)
    _migrate_stopped_users(con)
    _migrate_club_motto(con)
    _migrate_v20(con)
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


def default_club_id(db):
    return db.execute("SELECT MIN(id) FROM clubs").fetchone()[0]


def create_club(db, name):
    cur = db.execute("INSERT INTO clubs(name,created_at) VALUES(?,datetime('now'))", (name,))
    return cur.lastrowid


def create_team(db, name, season="", club_id=None):
    cur = db.execute("INSERT INTO teams(name,season,created_at,club_id) VALUES(?,?,datetime('now'),?)",
                     (name, season or None, club_id or default_club_id(db)))
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


ACTIVITY_RETENTION_DAYS = 180


SECURITY_RETENTION_DAYS = 30


def get_global(db, key, default=0):
    r = db.execute("SELECT value FROM settings WHERE key=?", (f"g:{key}",)).fetchone()
    try:
        return int(r["value"]) if r and r["value"] not in (None, "") else default
    except (ValueError, TypeError):
        return default


def set_global(db, key, value):
    db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (f"g:{key}", str(value)))


def purge_old(db):
    """Dataminimering: audit-log slettes efter 12 måneder; gamle loginforsøg ryddes."""
    db.execute("DELETE FROM audit_log WHERE ts < datetime('now','localtime',?)", (f"-{AUDIT_RETENTION_DAYS} days",))
    db.execute("DELETE FROM login_attempts WHERE ts < ?", (int(time.time()) - 3600,))
    db.execute("DELETE FROM reset_tokens WHERE expires_at < ?", (int(time.time()) - 86400,))
    db.execute("DELETE FROM login_fails WHERE ts < ?", (int(time.time()) - 3600,))
    db.execute("DELETE FROM revoked_sessions WHERE expires_at < ?", (int(time.time()),))
    months = get_global(db, "retention_months", 12)
    if months and get_global(db, "retention_auto", 0):
        n = db.execute("DELETE FROM players WHERE active=0 AND deactivated_at IS NOT NULL AND deactivated_at < date('now','localtime',?)", (f"-{months} months",)).rowcount
        if n:
            audit(db, "system", "inaktive_spillere_auto_slettet", f"antal={n}")
    db.execute("DELETE FROM security_events WHERE ts < ?", (int(time.time()) - SECURITY_RETENTION_DAYS * 86400,))
    db.execute("DELETE FROM activity WHERE slot < ?", (int(time.time()) // 900 - ACTIVITY_RETENTION_DAYS * 96,))
    db.commit()


def backup(db_path, backup_dir, keep=14):
    """Konsistent kopi af databasen via SQLite's backup-API. Beholder de seneste `keep` filer."""
    os.makedirs(backup_dir, exist_ok=True)
    dest = os.path.join(backup_dir, time.strftime("u11-%Y%m%d-%H%M%S.db"))
    n = 1
    while os.path.exists(dest):                        # to backups i samme sekund overskriver ikke hinanden
        dest = os.path.join(backup_dir, time.strftime("u11-%Y%m%d-%H%M%S") + f"-{n}.db")
        n += 1
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(dest)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    files = sorted(f for f in os.listdir(backup_dir) if f.startswith("u11-") and f.endswith(".db"))
    ok, msgs = verify_backup(dest)
    if not ok:                                        # en ødelagt backup må aldrig fortrænge en god
        os.remove(dest)
        raise RuntimeError("Backup fejlede kontrol: " + "; ".join(msgs))
    files = sorted(f for f in os.listdir(backup_dir) if f.startswith("u11-") and f.endswith(".db"))
    for old in files[:-keep]:
        os.remove(os.path.join(backup_dir, old))
    return dest


def verify_backup(path):
    """Kontrollerer en backupfil uden at ændre den: SQLite-integritet, fremmednøgler og skemaversion.
    Returnerer (ok, [meddelelser]). Bruges efter hver backup og af scripts/verify-backup.py før en gendannelse."""
    msgs = []
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return False, [f"Kan ikke åbne filen: {exc}"]
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            msgs.append("Integritetstjek fejlede.")
        if con.execute("PRAGMA foreign_key_check").fetchall():
            msgs.append("Fremmednøgler peger på rækker, der ikke findes.")
        ver = con.execute("PRAGMA user_version").fetchone()[0]
        if ver > SCHEMA_VERSION:
            msgs.append(f"Backup er fra en nyere version (skema {ver} > {SCHEMA_VERSION}).")
        for t in ("users", "teams", "players"):
            con.execute(f"SELECT COUNT(*) FROM {t}")
    except sqlite3.Error as exc:
        msgs.append(f"Ikke en gyldig Team Udvikling-database: {exc}")
    finally:
        con.close()
    return (not msgs), msgs


def backup_if_due(db_path, backup_dir, hours=24):
    os.makedirs(backup_dir, exist_ok=True)
    files = sorted(f for f in os.listdir(backup_dir) if f.startswith("u11-") and f.endswith(".db"))
    if files:
        age = time.time() - os.path.getmtime(os.path.join(backup_dir, files[-1]))
        if age < hours * 3600:
            return None
    return backup(db_path, backup_dir)


# ------------------------------------------------------------------ klubprofil (gælder alle hold)
DEFAULT_APP_NAME = "Team Udvikling"
CLUB_FIELDS = ("name", "app_name", "address", "email", "phone", "website", "footer", "color", "motto")


def club_get(db, club_id=None):
    """Klubprofil. Uden id: standardklubben (den ældste). Ukendt id → standardklubben (aldrig en fejl i skabeloner)."""
    row = db.execute("SELECT * FROM clubs WHERE id=?", (club_id,)).fetchone() if club_id else None
    row = row or db.execute("SELECT * FROM clubs ORDER BY id LIMIT 1").fetchone()
    out = {f: "" for f in CLUB_FIELDS + ("logo_mime", "logo_v")}
    out["id"] = None
    if row:
        out.update({k: (row[k] or "") for k in CLUB_FIELDS + ("logo_mime", "logo_v")})
        out["id"] = row["id"]
    out["app_name"] = out["app_name"].strip() or DEFAULT_APP_NAME
    return out


def club_set(db, club_id, key, value):
    if key not in CLUB_FIELDS + ("logo_mime", "logo_v"):
        raise ValueError(key)
    db.execute(f"UPDATE clubs SET {key}=? WHERE id=?", (value, club_id))
