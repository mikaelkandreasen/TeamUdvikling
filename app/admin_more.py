"""Administration (del 2): klubprofil, sikkerhedslog, e-mail, dataoprydning, import, «se som træner», evalueringsrunder og backlog.
Routes hører til samme blueprint som admin.py (endpoint-navne `admin.*` er uændrede); filen er udskilt for overskuelighedens skyld (B-11)."""
import io
import secrets
import time

from flask import Response, abort, current_app, flash, g, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import generate_password_hash

from . import activity, club, importer, mailer, model, remember, reset, reset_tokens, scope
from . import lockout
from .auth import _fresh_login, _too_many, admin_required, manager_required, revoke_session, throttled, verify_admin_code
from .db import audit, backup, club_get, club_set, create_club, create_team, default_club_id, get_db, set_setting
from .helpers import int_in, round_info, team_id
from .admin import _pick_club, _visible_clubs, bp

# ----------------------------------------------------------------------------- klubprofil
@bp.route("/club", methods=["GET", "POST"])
def club_profile():
    db = get_db()
    cid = _pick_club(db, request.values.get("club")) or (g.team["club_id"] if g.get("team") else None) or club_get(db)["id"]
    if not scope.can_manage_club(g.user, cid):
        abort(404)
    if request.method == "POST":
        action = request.form.get("action", "save")
        if action == "remove_logo":
            club.remove_logo(db, cid)
            audit(db, g.user["username"], "klublogo_fjernet")
            db.commit()
            flash("Logoet er fjernet.", "ok")
            return redirect(url_for("admin.club_profile", club=cid))
        problem = club.valid_color(request.form.get("color", "").strip())
        if problem:
            flash(problem, "error")
        else:
            limits = dict(name=80, app_name=60, address=160, email=120, phone=40, website=120, footer=300, motto=100)
            for k, n in limits.items():
                club_set(db, cid, k, (request.form.get(k) or "").strip()[:n])
            club_set(db, cid, "color", request.form.get("color", "").strip())
            upload = request.files.get("logo")
            if upload and upload.filename:
                err = club.save_logo(db, cid, upload.read(MAX_UPLOAD + 1))
                if err:
                    flash(err, "error")
                    db.commit()
                    return redirect(url_for("admin.club_profile", club=cid))
                audit(db, g.user["username"], "klublogo_uploadet")
            audit(db, g.user["username"], "klubprofil_gemt")
            db.commit()
            flash("Klubprofilen er gemt.", "ok")
        return redirect(url_for("admin.club_profile", club=cid))
    return render_template("admin_club.html", c=club_get(db, cid), cid=cid, clubs=_visible_clubs(db))


MAX_UPLOAD = club.MAX_LOGO_BYTES


@bp.route("/security")
@admin_required
def security():
    """Blokeringslog: IP-blokeringer, mislykkede login og låste konti de seneste 30 dage."""
    db = get_db()
    now = int(time.time())
    from datetime import datetime
    from zoneinfo import ZoneInfo
    zone = ZoneInfo(current_app.config.get("TIMEZONE") or "UTC")
    counts = db.execute("SELECT kind, SUM(ts>?) AS d1, SUM(ts>?) AS d7, COUNT(*) AS d30 FROM security_events GROUP BY kind ORDER BY kind", (now - 86400, now - 7 * 86400)).fetchall()
    top = db.execute("SELECT ip, COUNT(*) n FROM security_events GROUP BY ip ORDER BY n DESC LIMIT 10").fetchall()
    rows = [dict(r, when=datetime.fromtimestamp(r["ts"], zone).strftime("%d-%m-%Y %H:%M")) for r in db.execute("SELECT * FROM security_events ORDER BY ts DESC, id DESC LIMIT 100")]
    return render_template("admin_security.html", counts=counts, top=top, rows=rows)


@bp.route("/mail", methods=["GET", "POST"])
@admin_required
def mail_status():
    """E-mail-kø: antal i kø/fejlet/sendt og de seneste mails (uden indhold). Mislykkede kan sættes i kø igen."""
    from . import mail_queue
    db = get_db()
    if request.method == "POST":
        n = mail_queue.retry_failed(db)
        flash(f"{n} mails sat i kø igen." if n else "Ingen mails kan sættes i kø igen (indholdet slettes, når en mail opgives).", "ok" if n else "error")
        return redirect(url_for("admin.mail_status"))
    from datetime import datetime
    from zoneinfo import ZoneInfo
    zone = ZoneInfo(current_app.config.get("TIMEZONE") or "UTC")
    rows = [dict(r, when=datetime.fromtimestamp(r["created_at"], zone).strftime("%d-%m-%Y %H:%M"))
            for r in db.execute("SELECT id,to_addr,subject,kind,created_at,attempts,sent_at,failed,last_error FROM mail_queue ORDER BY id DESC LIMIT 100")]
    return render_template("admin_mail.html", st=mail_queue.stats(db), rows=rows)


# ----------------------------------------------------------------------------- dataoprydning (GDPR)
@bp.route("/retention", methods=["GET", "POST"])
def retention():
    """Opbevaringsfrist for inaktive spillere. Klubadministratorer ser og sletter kun egen klubs spillere."""
    from .db import get_global, set_global
    db = get_db()
    club_sql = "" if scope.is_sysadmin(g.user) else " AND t.club_id=%d" % int(g.user["club_id"])
    months = get_global(db, "retention_months", 12)
    overdue_sql = ("p.active=0 AND p.deactivated_at IS NOT NULL AND p.deactivated_at < date('now','localtime',?)" if months else "0")
    args = (f"-{months} months",) if months else ()
    if request.method == "POST":
        action = request.form.get("action", "delete_all")
        if action == "settings":
            if not scope.is_sysadmin(g.user):
                abort(403)
            m = int_in(request.form.get("months"), 0, 120) or 0
            set_global(db, "retention_months", m)
            set_global(db, "retention_auto", 1 if request.form.get("auto") and m else 0)
            audit(db, g.user["username"], "opbevaringsfrist_sat", f"{m} mdr, auto={1 if request.form.get('auto') and m else 0}")
            db.commit()
            flash("Opbevaringsfrist gemt.", "ok")
        elif request.form.get("confirm") != "ja":
            flash("Sletning kræver bekræftelse.", "error")
        else:
            where = overdue_sql if action == "delete_overdue" else "p.active=0"
            ids = [r["id"] for r in db.execute(f"SELECT p.id FROM players p JOIN teams t ON t.id=p.team_id WHERE {where}{club_sql}", args if action == "delete_overdue" else ())]  # nosec B608 – identifikatorer fra faste lister / kun ?-pladsholdere
            for pid in ids:
                db.execute("DELETE FROM players WHERE id=?", (pid,))
            audit(db, g.user["username"], "inaktive_spillere_slettet" if action == "delete_all" else "forfaldne_spillere_slettet", f"antal={len(ids)}")
            db.commit()
            flash(f"{len(ids)} spillere og alle deres data er slettet (kopier i automatiske backups forsvinder inden for 14 dage).", "ok")
        return redirect(url_for("admin.retention"))
    rows = db.execute(f"SELECT t.name tn, COUNT(*) n, SUM(CASE WHEN {overdue_sql} THEN 1 ELSE 0 END) due FROM players p JOIN teams t ON t.id=p.team_id "  # nosec B608 – identifikatorer fra faste lister / kun ?-pladsholdere
                      f"WHERE p.active=0{club_sql} GROUP BY t.id ORDER BY t.name", args).fetchall()
    return render_template("admin_retention.html", rows=rows, months=months, auto=get_global(db, "retention_auto", 0), sysadmin=scope.is_sysadmin(g.user),
                           due_total=sum((r["due"] or 0) for r in rows))


# ----------------------------------------------------------------------------- import af spillere/hold
def _import_club(db):
    """Klubben en import går til: klubadministratorens egen klub; for systemadministrator det aktive holds klub."""
    cid = scope.my_club(g.user) or (g.team["club_id"] if g.get("team") else None) or club_get(db)["id"]
    if not scope.can_manage_club(g.user, cid):
        abort(403)
    return cid


@bp.route("/import", methods=["GET", "POST"])
def import_data():
    db = get_db()
    cid = _import_club(db)
    if request.method == "POST":
        up = request.files.get("file")
        if not up or not up.filename:
            flash("Vælg en fil.", "error")
            return redirect(url_for("admin.import_data"))
        try:
            parsed = importer.classify(db, importer.parse(up.read(MAX_IMPORT + 1), up.filename, g.team["name"] if g.get("team") else ""), cid)
        except importer.ImportError_ as e:
            flash(str(e), "error")
            return redirect(url_for("admin.import_data"))
        token = importer.stash(current_app.config["U11_DATA_DIR"], g.user["id"], parsed)
        return render_template("admin_import_preview.html", p=parsed, token=token, shown=parsed["rows"][:100], club_name=club_get(db, cid)["name"])
    return render_template("admin_import.html", club_name=club_get(db, cid)["name"])


MAX_IMPORT = 1024 * 1024


@bp.route("/import/commit", methods=["POST"])
def import_commit():
    db = get_db()
    parsed = importer.unstash(current_app.config["U11_DATA_DIR"], g.user["id"], request.form.get("token", ""))
    if not parsed or request.form.get("confirm") != "ja":
        flash("Importen er udløbet eller ikke bekræftet. Upload filen igen.", "error")
        return redirect(url_for("admin.import_data"))
    cid = parsed.get("club_id")
    if not cid or cid != _import_club(db):                    # forhåndsvisningen hører til en anden klub (fx skiftet hold/profil imellem)
        flash("Importen hører til en anden klub. Upload filen igen.", "error")
        return redirect(url_for("admin.import_data"))
    new_n, upd_n, team_n = importer.apply(db, parsed, cid)
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
    u = db.execute("SELECT * FROM users WHERE id=? AND role='trainer' AND stopped_at IS NULL", (uid,)).fetchone()
    if not u or not scope.can_manage_user(g.user, u):
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
                label = (request.form.get("label") or "").strip()[:60]
                day = (request.form.get("date") or "").strip()
                if not label or not model.parse_date(day):
                    flash("Giv runden et navn og en dato.", "error")
                    return redirect(url_for("admin.evaluations"))
                set_setting(db, tid, "rounds_n", str(n + 1))
                set_setting(db, tid, f"round_label_{n + 1}", label)
                set_setting(db, tid, f"round_date_{n + 1}", day)
                audit(db, g.user["username"], "runde_tilfoejet", f"{g.team['name']}: {n + 1}")
                flash(f"Runde {n + 1} er tilføjet.", "ok")
        elif action == "remove_round":
            if n <= 2:
                flash("Der skal mindst være 2 runder.", "error")
            elif request.form.get("confirm") != "ja":
                flash("Bekræft, at runden og dens evalueringer skal slettes.", "error")
            else:
                db.execute("DELETE FROM evaluations WHERE round=? AND player_id IN (SELECT id FROM players WHERE team_id=?)", (n, tid))
                db.execute("DELETE FROM level_ratings WHERE round=? AND player_id IN (SELECT id FROM players WHERE team_id=?)", (n, tid))
                db.execute("DELETE FROM dbu_checks WHERE round=? AND player_id IN (SELECT id FROM players WHERE team_id=?)", (n, tid))
                db.execute("DELETE FROM settings WHERE key IN (?,?,?)", (f"t{tid}:round_label_{n}", f"t{tid}:round_date_{n}", f"t{tid}:round_opened_{n}"))
                db.execute("DELETE FROM settings WHERE key=?", (f"t{tid}:assist_ok_{n}",))
                set_setting(db, tid, "rounds_n", str(n - 1))
                audit(db, g.user["username"], "runde_fjernet", f"{g.team['name']}: runde {n}")
                flash(f"Runde {n} og dens evalueringer er slettet.", "ok")
        elif action == "assist":
            rnd = request.form.get("round", type=int)
            if rnd not in g.rounds:
                abort(404)
            valid = {r[0] for r in db.execute("SELECT id FROM users WHERE readonly=1")}
            inc = sorted({int(x) for x in request.form.getlist("inc") if x.isdigit()} & valid)
            set_setting(db, tid, f"assist_ok_{rnd}", ",".join(map(str, inc)))
            audit(db, g.user["username"], "assistent_medtaget", f"{g.team['name']}: runde {rnd}, brugere={inc}")
            flash("Valget er gemt. Holdets og spillernes samlede score er opdateret.", "ok")
        elif action == "reopen_round":
            rnd = request.form.get("round", type=int)
            if rnd not in g.rounds:
                abort(404)
            from datetime import date
            set_setting(db, tid, f"round_opened_{rnd}", date.today().isoformat())
            audit(db, g.user["username"], "runde_genaabnet", f"{g.team['name']}: runde {rnd}")
            flash("Runden er genåbnet i 30 dage.", "ok")
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
                db.execute(sql.replace("evaluations", "level_ratings") + ")", args)
                db.execute(sql.replace("evaluations", "dbu_checks") + ")", args)
                audit(db, g.user["username"], "evalueringer_slettet", f"{g.team['name']}: runde {rnd}, rækker={cur.rowcount}")
                flash(f"{cur.rowcount} scores slettet.", "ok")
        db.commit()
        return redirect(url_for("admin.evaluations"))
    counts = db.execute("SELECT e.round, e.trainer_id, u.display_name, u.readonly, COUNT(DISTINCT e.player_id) players, COUNT(*) n FROM evaluations e "
                        "JOIN players p ON p.id=e.player_id JOIN users u ON u.id=e.trainer_id WHERE p.team_id=? "
                        "GROUP BY e.round, e.trainer_id ORDER BY e.round, u.display_name", (tid,)).fetchall()
    trainers = db.execute("SELECT DISTINCT u.id, u.display_name FROM evaluations e JOIN players p ON p.id=e.player_id "
                          "JOIN users u ON u.id=e.trainer_id WHERE p.team_id=? ORDER BY u.display_name", (tid,)).fetchall()
    players = db.execute("SELECT id, name FROM players WHERE team_id=? ORDER BY name COLLATE NOCASE", (tid,)).fetchall()
    skip = model.excluded_assistants(db, tid)
    assist = []
    for rnd in sorted({c["round"] for c in counts if c["readonly"]}):
        assist.append(dict(rnd=rnd, label=round_info(db)[rnd - 1]["label"],
                           rows=[dict(id=c["trainer_id"], name=c["display_name"], players=c["players"], included=c["trainer_id"] not in skip.get(rnd, ()))
                                 for c in counts if c["round"] == rnd and c["readonly"]]))
    return render_template("admin_evaluations.html", counts=counts, assist=assist, trainers=trainers, players=players, infos=round_info(db),
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
@admin_required
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
