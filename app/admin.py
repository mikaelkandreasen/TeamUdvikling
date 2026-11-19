"""Administration: hold, brugere (med holdtilknytning), runder, backup, Excel-eksport og revisionslog."""
import io
import secrets
import time

from flask import Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import generate_password_hash

from . import club, importer, mailer, model, remember, reset, reset_tokens
from . import lockout
from .auth import _too_many, admin_required, revoke_session, throttled, verify_admin_code
from .db import audit, backup, club_get, club_set, create_team, get_db, set_setting
from .helpers import round_info, team_id

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.before_request
@admin_required
def _guard():
    return None


@bp.route("/")
def index():
    return render_template("admin_index.html")


# ----------------------------------------------------------------------------- hold
def _team_rows(db):
    return db.execute(
        "SELECT t.*, (SELECT COUNT(*) FROM players p WHERE p.team_id=t.id) AS players, "
        "(SELECT COUNT(*) FROM user_teams ut WHERE ut.team_id=t.id) AS trainers FROM teams t ORDER BY t.name COLLATE NOCASE").fetchall()


@bp.route("/teams", methods=["GET", "POST"])
def teams():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:80]
        if not name:
            flash("Holdnavn mangler.", "error")
        elif db.execute("SELECT 1 FROM teams WHERE name=?", (name,)).fetchone():
            flash("Der findes allerede et hold med det navn.", "error")
        else:
            create_team(db, name, request.form.get("season", "").strip()[:20])
            audit(db, g.user["username"], "hold_oprettet", name)
            db.commit()
            flash(f"Holdet '{name}' er oprettet.", "ok")
            return redirect(url_for("admin.teams"))
    return render_template("admin_teams.html", teams=_team_rows(db))


@bp.route("/teams/<int:tid>/<action>", methods=["POST"])
def team_action(tid, action):
    db = get_db()
    t = db.execute("SELECT * FROM teams WHERE id=?", (tid,)).fetchone()
    if not t:
        abort(404)
    if action == "rename":
        name = request.form.get("name", "").strip()[:80]
        clash = db.execute("SELECT 1 FROM teams WHERE name=? AND id<>?", (name, tid)).fetchone()
        if not name or clash:
            flash("Ugyldigt eller optaget holdnavn.", "error")
        else:
            db.execute("UPDATE teams SET name=?, season=? WHERE id=?", (name, request.form.get("season", "").strip()[:20] or None, tid))
            audit(db, g.user["username"], "hold_omdøbt", f"{t['name']} -> {name}")
            flash("Gemt.", "ok")
    elif action == "delete":
        if request.form.get("confirm", "").strip() != t["name"]:
            flash("Skriv holdets navn præcist for at bekræfte sletning.", "error")
        else:
            db.execute("DELETE FROM settings WHERE key LIKE ?", (f"t{tid}:%",))
            db.execute("DELETE FROM teams WHERE id=?", (tid,))  # CASCADE: spillere, evalueringer, svar, udviklingsdata
            audit(db, g.user["username"], "hold_slettet", t["name"])
            flash(f"Holdet '{t['name']}' og alle dets data er slettet.", "ok")
    else:
        abort(404)
    db.commit()
    return redirect(url_for("admin.teams"))


# --------------------------------------------------------------------------- brugere
def _render_users(db, temp=None, temp_user=None):
    users = db.execute("SELECT * FROM users ORDER BY username").fetchall()
    mem = {}
    for r in db.execute("SELECT user_id, team_id FROM user_teams"):
        mem.setdefault(r["user_id"], set()).add(r["team_id"])
    return render_template("admin_users.html", users=users, mem=mem, all_teams=_team_rows(db), temp=temp, temp_user=temp_user,
                           mail_missing=mailer.missing())


def _set_user_teams(db, uid, team_ids):
    valid = {r["id"] for r in db.execute("SELECT id FROM teams")}
    db.execute("DELETE FROM user_teams WHERE user_id=?", (uid,))
    for t in {int(x) for x in team_ids if str(x).isdigit()} & valid:
        db.execute("INSERT INTO user_teams(user_id,team_id) VALUES(?,?)", (uid, t))


@bp.route("/users", methods=["GET", "POST"])
def users():
    db = get_db()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        name = request.form.get("display_name", "").strip() or username
        role = "admin" if request.form.get("role") == "admin" else "trainer"
        email, email_err = mailer.normalize_email(request.form.get("email"))
        if not username:
            flash("Brugernavn mangler.", "error")
        elif email_err:
            flash(email_err, "error")
        elif db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            flash("Brugernavnet findes allerede.", "error")
        else:
            temp = secrets.token_urlsafe(12)
            cur = db.execute("INSERT INTO users(username,display_name,pw_hash,role,must_change_pw,created_at,email) VALUES(?,?,?,?,1,datetime('now'),?)",
                             (username, name, generate_password_hash(temp), role, email))
            _set_user_teams(db, cur.lastrowid, request.form.getlist("teams"))
            audit(db, g.user["username"], "bruger_oprettet", f"{username} ({role})")
            db.commit()
            flash(f"Bruger '{username}' oprettet. Midlertidig adgangskode vises kun nu.", "ok")
            return _render_users(db, temp, username)
    return _render_users(db)


@bp.route("/users/<int:uid>/<action>", methods=["POST"])
def user_action(uid, action):
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        abort(404)
    temp = None
    if action == "teams":
        _set_user_teams(db, uid, request.form.getlist("teams"))
        flash("Holdtilknytning gemt.", "ok")
    elif action == "email":
        email, err = mailer.normalize_email(request.form.get("email"))
        if err:
            flash(err, "error")
            return redirect(url_for("admin.users"))
        db.execute("UPDATE users SET email=? WHERE id=?", (email, uid))
        reset_tokens.revoke_user(db, uid)                 # afventende links gik til den gamle adresse
        flash("E-mailadresse gemt." if email else "E-mailadresse fjernet.", "ok")
    elif action == "mail-reset":
        purpose = request.form.get("purpose")
        if purpose not in ("password", "totp"):
            abort(400)
        if throttled(db):
            return _too_many()
        if not verify_admin_code(db, g.user, request.form.get("code", "")):
            if lockout.is_locked(db, db.execute("SELECT * FROM users WHERE id=?", (g.user["id"],)).fetchone()):
                revoke_session(db)
                db.commit()
                session.clear()                           # for mange forkerte koder → ud
                return redirect(url_for("auth.login"))
            flash("Forkert eller allerede brugt 2FA-kode. Vent på en ny kode i appen og prøv igen.", "error")
            return redirect(url_for("admin.users"))
        ok, msg = reset.send_reset(db, u, purpose, g.user["username"])
        audit(db, g.user["username"], "mail_nulstil_sendt" if ok else "mail_nulstil_fejlet", f"{u['username']} ({purpose})")
        db.commit()
        flash(msg, "ok" if ok else "error")
        return redirect(url_for("admin.users"))
    elif action == "reset-2fa":
        db.execute("UPDATE users SET totp_secret=NULL, totp_enabled=0, last_totp_step=0 WHERE id=?", (uid,))
        db.execute("DELETE FROM recovery_codes WHERE user_id=?", (uid,))
        remember.revoke_user(db, uid)
        reset_tokens.revoke_user(db, uid)
        flash("2FA nulstillet – brugeren skal oprette den igen ved næste login.", "ok")
    elif action == "reset-password":
        temp = secrets.token_urlsafe(12)
        db.execute("UPDATE users SET pw_hash=?, must_change_pw=1 WHERE id=?", (generate_password_hash(temp), uid))
        remember.revoke_user(db, uid)
        reset_tokens.revoke_user(db, uid)
        flash("Adgangskode nulstillet. Den midlertidige kode vises kun nu.", "ok")
    elif action == "unlock":
        lockout.clear(db, uid, all_ips=True)
        flash("Konto låst op.", "ok")
    elif action == "delete":
        if uid == g.user["id"]:
            flash("Du kan ikke slette dig selv.", "error")
            return redirect(url_for("admin.users"))
        if u["role"] == "admin" and db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] <= 1:
            flash("Der skal altid være mindst én administrator.", "error")
            return redirect(url_for("admin.users"))
        db.execute("DELETE FROM users WHERE id=?", (uid,))
        flash("Bruger slettet (træners egne evalueringer slettes også).", "ok")
    else:
        abort(404)
    audit(db, g.user["username"], f"bruger_{action}", u["username"])
    db.commit()
    return _render_users(db, temp, u["username"] if temp else None)


# ------------------------------------------------------------------- indstillinger mv.
@bp.route("/settings", methods=["GET", "POST"])
def settings():
    db = get_db()
    tid = team_id()
    if request.method == "POST":
        for r in g.rounds:
            set_setting(db, tid, f"round_label_{r}", (request.form.get(f"label_{r}") or "").strip()[:60])
            d = (request.form.get(f"date_{r}") or "").strip()
            set_setting(db, tid, f"round_date_{r}", d if model.parse_date(d) else "")
        db.commit()
        flash("Gemt.", "ok")
        return redirect(url_for("admin.settings"))
    return render_template("admin_settings.html", infos=round_info(db))


@bp.route("/backup", methods=["POST"])
def make_backup():
    dest = backup(current_app.config["DATABASE"], current_app.config["BACKUP_DIR"])
    audit(get_db(), g.user["username"], "backup_hentet")
    get_db().commit()
    return send_file(dest, as_attachment=True, download_name="u11-backup.db")


@bp.route("/audit")
def audit_log():
    rows = get_db().execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 300").fetchall()
    return render_template("admin_audit.html", rows=rows)


def _append(ws, row):
    """Tilføj række; tekst der starter med '=' gemmes som ren tekst (beskyttelse mod formel-injektion i Excel)."""
    ws.append(row)
    for c in ws[ws.max_row]:
        if isinstance(c.value, str) and c.value[:1] in ("=", "+", "-", "@"):
            c.data_type = "s"


@bp.route("/export.xlsx")
def export_xlsx():
    """Excel-eksport af det aktive holds data."""
    from openpyxl import Workbook
    db = get_db()
    tid = team_id()
    wb = Workbook()
    ws = wb.active
    ws.title = "Spillere"
    _append(ws, ["Id", "Navn", "Fødselsdato", "Trøje", "Position", "Sekundær", "Fod", "Startdato", "Fokus 1", "Fokus 2", "Noter", "Aktiv"])
    for p in db.execute("SELECT * FROM players WHERE team_id=? ORDER BY name COLLATE NOCASE", (tid,)):
        _append(ws, [p["id"], p["name"], p["birth_date"], p["shirt_no"], p["position"], p["position2"], p["foot"],
                   p["start_date"], p["focus1"], p["focus2"], p["notes"], p["active"]])
    ws = wb.create_sheet("Evalueringer")
    _append(ws, ["Runde", "Spiller", "Træner", "Rolle", "Nøglefærdighed", "Score"])
    for r in db.execute("SELECT e.round, p.name pn, u.display_name un, e.crit, e.score FROM evaluations e "
                        "JOIN players p ON p.id=e.player_id JOIN users u ON u.id=e.trainer_id WHERE p.team_id=? "
                        "ORDER BY e.round, p.name, u.display_name, e.crit", (tid,)):
        c = model.CRITERIA[r["crit"]]
        _append(ws, [r["round"], r["pn"], r["un"], c["role"], c["skill"], r["score"]])
    ws = wb.create_sheet("Teamoversigt")
    _append(ws, ["Runde", "Spiller"] + model.ROLES + ["Samlet", "Enighed", "Fortolkning"])
    rounds = model.load_rounds(db, tid)
    names = {p["id"]: p["name"] for p in db.execute("SELECT id,name FROM players WHERE team_id=?", (tid,))}
    for rnd in g.rounds:
        for pid, res in sorted(rounds[rnd].items(), key=lambda kv: names.get(kv[0], "")):
            _append(ws, [rnd, names.get(pid)] + [None if v is None else round(v, 2) for v in res["roles"]] +
                      [None if res["samlet"] is None else round(res["samlet"], 2),
                       None if res["enighed"] is None else round(res["enighed"], 2), res["fortolkning"]])
    ws = wb.create_sheet("Motivation")
    _append(ws, ["Spiller", "Kategori", "Spørgsmål", "Score"])
    for r in db.execute("SELECT p.name pn, c.title, q.text, a.score FROM motivation_answers a JOIN players p ON p.id=a.player_id "
                        "JOIN motivation_questions q ON q.qidx=a.qidx AND q.team_id=p.team_id "
                        "JOIN motivation_categories c ON c.cat=q.cat AND c.team_id=p.team_id WHERE p.team_id=? ORDER BY p.name, q.qidx", (tid,)):
        _append(ws, [r["pn"], r["title"], r["text"], r["score"]])
    ws = wb.create_sheet("Udviklingsdata")
    _append(ws, ["Spiller", "Træninger", "Kampe"] + model.TRIVSEL + model.MOTORIK + ["Tiltag", "Spillerens mål", "Opfølgning", "Status"])
    for r in db.execute("SELECT p.name, d.* FROM devdata d JOIN players p ON p.id=d.player_id WHERE p.team_id=? ORDER BY p.name", (tid,)):
        _append(ws, [r["name"], r["trainings"], r["matches"], r["t1"], r["t2"], r["t3"], r["m1"], r["m2"], r["m3"], r["m4"],
                   r["tiltag"], r["eget_maal"], r["followup"], r["status"]])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    audit(db, g.user["username"], "excel_eksport", g.team["name"])
    db.commit()
    return send_file(buf, as_attachment=True, download_name=f"u11-eksport-{g.team['name']}.xlsx".replace(" ", "_").replace("/", "-"),
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ----------------------------------------------------------------------------- klubprofil
@bp.route("/club", methods=["GET", "POST"])
def club_profile():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action", "save")
        if action == "remove_logo":
            club.remove_logo(db)
            audit(db, g.user["username"], "klublogo_fjernet")
            db.commit()
            flash("Logoet er fjernet.", "ok")
            return redirect(url_for("admin.club_profile"))
        problem = club.valid_color(request.form.get("color", "").strip())
        if problem:
            flash(problem, "error")
        else:
            limits = dict(name=80, address=160, email=120, phone=40, website=120, footer=300)
            for k, n in limits.items():
                club_set(db, k, (request.form.get(k) or "").strip()[:n])
            club_set(db, "color", request.form.get("color", "").strip())
            upload = request.files.get("logo")
            if upload and upload.filename:
                err = club.save_logo(db, upload.read(MAX_UPLOAD + 1))
                if err:
                    flash(err, "error")
                    db.commit()
                    return redirect(url_for("admin.club_profile"))
                audit(db, g.user["username"], "klublogo_uploadet")
            audit(db, g.user["username"], "klubprofil_gemt")
            db.commit()
            flash("Klubprofilen er gemt.", "ok")
        return redirect(url_for("admin.club_profile"))
    return render_template("admin_club.html", c=club_get(db))


MAX_UPLOAD = club.MAX_LOGO_BYTES


# ----------------------------------------------------------------------------- dataoprydning (GDPR)
@bp.route("/retention", methods=["GET", "POST"])
def retention():
    db = get_db()
    if request.method == "POST":
        if request.form.get("confirm") != "ja":
            flash("Sletning kræver bekræftelse.", "error")
        else:
            n = db.execute("SELECT COUNT(*) FROM players WHERE active=0").fetchone()[0]
            db.execute("DELETE FROM players WHERE active=0")
            audit(db, g.user["username"], "inaktive_spillere_slettet", f"antal={n}")
            db.commit()
            flash(f"{n} inaktive spillere og alle deres data er slettet (kopier i automatiske backups forsvinder inden for 14 dage).", "ok")
        return redirect(url_for("admin.retention"))
    rows = db.execute("SELECT t.name tn, COUNT(*) n FROM players p JOIN teams t ON t.id=p.team_id WHERE p.active=0 GROUP BY t.id ORDER BY t.name").fetchall()
    return render_template("admin_retention.html", rows=rows)


# ----------------------------------------------------------------------------- import af spillere/hold
@bp.route("/import", methods=["GET", "POST"])
def import_data():
    db = get_db()
    if request.method == "POST":
        up = request.files.get("file")
        if not up or not up.filename:
            flash("Vælg en fil.", "error")
            return redirect(url_for("admin.import_data"))
        try:
            parsed = importer.classify(db, importer.parse(up.read(MAX_IMPORT + 1), up.filename, g.team["name"] if g.get("team") else ""))
        except importer.ImportError_ as e:
            flash(str(e), "error")
            return redirect(url_for("admin.import_data"))
        token = importer.stash(current_app.config["U11_DATA_DIR"], g.user["id"], parsed)
        return render_template("admin_import_preview.html", p=parsed, token=token, shown=parsed["rows"][:100])
    return render_template("admin_import.html")


MAX_IMPORT = 1024 * 1024


@bp.route("/import/commit", methods=["POST"])
def import_commit():
    db = get_db()
    parsed = importer.unstash(current_app.config["U11_DATA_DIR"], g.user["id"], request.form.get("token", ""))
    if not parsed or request.form.get("confirm") != "ja":
        flash("Importen er udløbet eller ikke bekræftet. Upload filen igen.", "error")
        return redirect(url_for("admin.import_data"))
    new_n, upd_n, team_n = importer.apply(db, parsed)
    audit(db, g.user["username"], "import", f"nye={new_n} opdateret={upd_n} nye_hold={team_n}")
    db.commit()
    flash(f"Import gennemført: {new_n} nye spillere, {upd_n} opdateret, {team_n} nye hold.", "ok")
    return redirect(url_for("admin.teams"))


@bp.route("/import/template.<fmt>")
def import_template(fmt):
    if fmt == "csv":
        return Response(importer.template_csv(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=spillere-skabelon.csv"})
    if fmt == "xlsx":
        return Response(importer.template_xlsx(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": "attachment; filename=spillere-skabelon.xlsx"})
    abort(404)


# ----------------------------------------------------------------------------- se siden som træner
@bp.route("/users/<int:uid>/view-as", methods=["POST"])
def view_as(uid):
    from flask import session
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE id=? AND role='trainer'", (uid,)).fetchone()
    if not u:
        abort(404)
    session["view_as"] = uid
    audit(db, g.user["username"], "se_som_traener", u["username"])
    db.commit()
    return redirect(url_for("main.home"))


# ----------------------------------------------------------------------------- evalueringsrunder og -data
@bp.route("/evaluations", methods=["GET", "POST"])
def evaluations():
    from .teams import team_rounds
    db = get_db()
    tid = team_id()
    n = len(g.rounds)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add_round":
            if n >= model.MAX_ROUNDS:
                flash(f"Der kan højst være {model.MAX_ROUNDS} runder.", "error")
            else:
                set_setting(db, tid, "rounds_n", str(n + 1))
                audit(db, g.user["username"], "runde_tilfoejet", f"{g.team['name']}: {n + 1}")
                flash(f"Runde {n + 1} er tilføjet.", "ok")
        elif action == "remove_round":
            if n <= 2:
                flash("Der skal mindst være 2 runder.", "error")
            elif request.form.get("confirm") != "ja":
                flash("Bekræft, at runden og dens evalueringer skal slettes.", "error")
            else:
                db.execute("DELETE FROM evaluations WHERE round=? AND player_id IN (SELECT id FROM players WHERE team_id=?)", (n, tid))
                db.execute("DELETE FROM settings WHERE key IN (?,?)", (f"t{tid}:round_label_{n}", f"t{tid}:round_date_{n}"))
                set_setting(db, tid, "rounds_n", str(n - 1))
                audit(db, g.user["username"], "runde_fjernet", f"{g.team['name']}: runde {n}")
                flash(f"Runde {n} og dens evalueringer er slettet.", "ok")
        elif action == "delete_evals":
            rnd = request.form.get("round", type=int)
            trainer = request.form.get("trainer", type=int)
            pid = request.form.get("player", type=int)
            if rnd not in g.rounds or not trainer:
                flash("Vælg runde og træner.", "error")
            elif request.form.get("confirm") != "ja":
                flash("Bekræft sletningen.", "error")
            else:
                sql = "DELETE FROM evaluations WHERE round=? AND trainer_id=? AND player_id IN (SELECT id FROM players WHERE team_id=?"
                args = [rnd, trainer, tid]
                if pid:
                    sql += " AND id=?"
                    args.append(pid)
                cur = db.execute(sql + ")", args)
                audit(db, g.user["username"], "evalueringer_slettet", f"{g.team['name']}: runde {rnd}, rækker={cur.rowcount}")
                flash(f"{cur.rowcount} scores slettet.", "ok")
        db.commit()
        return redirect(url_for("admin.evaluations"))
    counts = db.execute("SELECT e.round, e.trainer_id, u.display_name, COUNT(DISTINCT e.player_id) players, COUNT(*) n FROM evaluations e "
                        "JOIN players p ON p.id=e.player_id JOIN users u ON u.id=e.trainer_id WHERE p.team_id=? "
                        "GROUP BY e.round, e.trainer_id ORDER BY e.round, u.display_name", (tid,)).fetchall()
    trainers = db.execute("SELECT DISTINCT u.id, u.display_name FROM evaluations e JOIN players p ON p.id=e.player_id "
                          "JOIN users u ON u.id=e.trainer_id WHERE p.team_id=? ORDER BY u.display_name", (tid,)).fetchall()
    players = db.execute("SELECT id, name FROM players WHERE team_id=? ORDER BY name COLLATE NOCASE", (tid,)).fetchall()
    return render_template("admin_evaluations.html", counts=counts, trainers=trainers, players=players, infos=round_info(db),
                           can_add=n < model.MAX_ROUNDS, can_remove=n > 2)


# ----------------------------------------------------------------------------- backlog (prioriterbar)
BACKLOG_STATUS = ["Ny", "I gang", "Færdig"]
BACKLOG_PRIO = {0: "P0 – kritisk", 1: "P1 – vigtig", 2: "P2 – senere", 3: "Idé"}


def _seed_backlog(db):
    from .db import get_setting
    if get_setting(db, 0, "backlog_seeded"):
        return
    from .backlog_seed import SEED
    for i, (prio, title, desc) in enumerate(SEED):
        db.execute("INSERT INTO backlog_items(title,description,priority,status,position,created_at) VALUES(?,?,?,?,?,datetime('now'))",
                   (title, desc, prio, "Ny", i))
    set_setting(db, 0, "backlog_seeded", "1")
    db.commit()


@bp.route("/backlog", methods=["GET", "POST"])
def backlog():
    db = get_db()
    _seed_backlog(db)
    if request.method == "POST":
        action = request.form.get("action")
        iid = request.form.get("id", type=int)
        if action == "add":
            title = (request.form.get("title") or "").strip()[:140]
            if title:
                prio = request.form.get("priority", type=int)
                pos = db.execute("SELECT COALESCE(MAX(position),0)+1 FROM backlog_items").fetchone()[0]
                db.execute("INSERT INTO backlog_items(title,description,priority,status,position,created_at) VALUES(?,?,?,?,?,datetime('now'))",
                           (title, (request.form.get("description") or "").strip()[:2000], prio if prio in BACKLOG_PRIO else 2, "Ny", pos))
            else:
                flash("Titel mangler.", "error")
        elif iid and db.execute("SELECT 1 FROM backlog_items WHERE id=?", (iid,)).fetchone():
            if action == "save":
                prio = request.form.get("priority", type=int)
                status = request.form.get("status")
                db.execute("UPDATE backlog_items SET title=?, description=?, priority=?, status=? WHERE id=?",
                           ((request.form.get("title") or "").strip()[:140] or "(uden titel)", (request.form.get("description") or "").strip()[:2000],
                            prio if prio in BACKLOG_PRIO else 2, status if status in BACKLOG_STATUS else "Ny", iid))
            elif action in ("up", "down"):
                me = db.execute("SELECT * FROM backlog_items WHERE id=?", (iid,)).fetchone()
                rows = db.execute("SELECT id FROM backlog_items WHERE priority=? ORDER BY position, id", (me["priority"],)).fetchall()
                ids = [r["id"] for r in rows]
                i = ids.index(iid)
                j = i - 1 if action == "up" else i + 1
                if 0 <= j < len(ids):
                    ids[i], ids[j] = ids[j], ids[i]
                    for pos, x in enumerate(ids):
                        db.execute("UPDATE backlog_items SET position=? WHERE id=?", (pos, x))
            elif action == "delete":
                db.execute("DELETE FROM backlog_items WHERE id=?", (iid,))
        db.commit()
        return redirect(url_for("admin.backlog") + (f"#i{iid}" if iid and action != "delete" else ""))
    items = db.execute("SELECT * FROM backlog_items ORDER BY (status='Færdig'), priority, position, id").fetchall()
    return render_template("admin_backlog.html", items=items, prios=BACKLOG_PRIO, statuses=BACKLOG_STATUS)
