"""Holdets side: indstillinger (chef-træner), noter, spillerniveau, slogan og mascot med rapport."""
import datetime
import json

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from . import criteria as criteria_mod, heatcfg, photos, features, formations, ical, levels as levelcalc, model, motivation, scope
from .db import audit, get_db, get_setting, set_setting
from .helpers import active_players, int_in, round_info, team_id

bp = Blueprint("team", __name__, url_prefix="/team")


def can_configure():
    """Chef-træner for det aktive hold, klubadministrator for holdets klub eller systemadministrator."""
    if not g.get("team") or not g.get("user") or g.get("viewing") or g.user["readonly"]:
        return False
    return scope.can_manage_club(g.user, g.team["club_id"]) or g.team["id"] in scope.head_team_ids(get_db(), g.user)


def _need_config():
    if not can_configure():
        abort(403)


@bp.app_context_processor
def _ctx():
    return dict(can_configure=can_configure)


def profile(db, tid):
    """Holdprofil: spillere på banen (kamptype) og antal udskiftere."""
    gt = get_setting(db, tid, "game_type")
    gt = gt if gt in formations.GAME_TYPES else formations.DEFAULT_TYPE
    subs = int_in(get_setting(db, tid, "subs"), 0, 10)
    return dict(game_type=gt, size=formations.GAME_TYPES[gt], subs=2 if subs is None else subs)


@bp.route("/")
def index():
    return render_template("team_index.html", prof=profile(get_db(), team_id()), n_players=len(active_players(get_db())))


def focus_data(db, tid, players):
    """Forslag til træningsfokus: holdets laveste kriterier i seneste runde med data + spillernes højeste ønsker (kun for dette hold)."""
    rounds = model.load_rounds(db, tid)
    ids = [p["id"] for p in players]
    rnd = next((r for r in reversed(g.rounds) if any(i in rounds[r] and rounds[r][i]["samlet"] is not None for i in ids)), None)
    crit, n = [], 0
    if rnd:
        res = [rounds[rnd][i] for i in ids if i in rounds[rnd] and rounds[rnd][i]["samlet"] is not None]
        n = len(res)
        crit = sorted([(c, model.mean([x["crit"][c["idx"]] for x in res])) for c in model.CRITERIA], key=lambda t: (t[1] is None, t[1]))
        crit = [t for t in crit if t[1] is not None]
    wishes = []
    cats, qs = motivation.load_questions(db, tid)
    ans = {}
    for r in db.execute("SELECT a.player_id, a.qidx, a.score FROM motivation_answers a JOIN players p ON p.id=a.player_id WHERE p.team_id=?", (tid,)):
        if r["player_id"] in ids:
            ans.setdefault(r["qidx"], []).append(r["score"])
    for q in qs:
        v = ans.get(q["qidx"])
        if q["text"].strip() and v:
            wishes.append(dict(text=q["text"], cat=cats.get(q["cat"], ""), avg=model.mean(v), n=len(v)))
    wishes.sort(key=lambda w: -w["avg"])
    return dict(rnd=rnd, n=n, lowest=crit[:5], highest=list(reversed(crit[-3:])), wishes=wishes[:5])


def team_focus(db, tid):
    """Det fokus trænerne har valgt for holdet: {items: [tekst, …], updated: dato}. Tom liste hvis intet er valgt."""
    raw = get_setting(db, tid, "focus_items") or ""
    return dict(items=[x for x in raw.split("\n") if x.strip()][:4], updated=get_setting(db, tid, "focus_updated") or "")


@bp.route("/focus", methods=["GET", "POST"])
def focus():
    db = get_db()
    tid = team_id()
    data = focus_data(db, tid, active_players(db))
    if request.method == "POST":
        if g.user["readonly"]:
            abort(403)
        names = {f"{c['skill']} som {c['role'].lower()}" for c, _ in data["lowest"] + data["highest"]}
        picked = [x for x in request.form.getlist("pick") if x in names]
        own = (request.form.get("own") or "").strip().replace("\n", " ")[:80]
        items = (picked + ([own] if own else []))[:4]
        set_setting(db, tid, "focus_items", "\n".join(items))
        set_setting(db, tid, "focus_updated", datetime.date.today().isoformat() if items else "")
        audit(db, g.user["username"], "holdfokus_gemt", g.team["name"])
        db.commit()
        flash("Holdets fokus er gemt." if items else "Holdets fokus er ryddet.", "ok")
        return redirect(url_for("team.focus"))
    cur = team_focus(db, tid)
    names = {f"{c['skill']} som {c['role'].lower()}" for c, _ in data["lowest"] + data["highest"]}
    return render_template("team_focus.html", infos=round_info(db), current=cur, own_prev=next((x for x in cur["items"] if x not in names), ""), **data)


@bp.route("/settings", methods=["GET", "POST"])
def settings():
    _need_config()
    db = get_db()
    tid = team_id()
    if request.method == "POST":
        gt = request.form.get("game_type")
        subs = int_in(request.form.get("subs"), 0, 10)
        if gt not in formations.GAME_TYPES or subs is None:
            flash("Vælg kamptype og antal udskiftere (0–10).", "error")
            return redirect(url_for("team.settings"))
        set_setting(db, tid, "game_type", gt)
        set_setting(db, tid, "subs", str(subs))
        sa, sc = int_in(request.form.get("level_share_a"), 0, 45), int_in(request.form.get("level_share_c"), 0, 45)
        if sa is not None and sc is not None:
            set_setting(db, tid, "level_share_a", str(sa))
            set_setting(db, tid, "level_share_c", str(sc))
        else:
            flash("Andel til A og C skal være mellem 0 og 45 %. De blev ikke ændret.", "error")
        for k in features.KEYS:
            set_setting(db, tid, f"feat_{k}", "1" if request.form.get(f"feat_{k}") else "0")
        url = (request.form.get("ical_url") or "").strip()[:500]
        if url:
            try:
                ical.check_url(url)
            except ical.FeedError as exc:
                flash(f"Kalenderadressen blev ikke gemt: {exc}", "error")
                url = ""
        if url != (get_setting(db, tid, "ical_url") or ""):
            set_setting(db, tid, "ical_fetched_at", "")             # nyt link: hent forfra ved næste kampforslag
        set_setting(db, tid, "ical_url", url)
        db.execute("UPDATE teams SET slogan=?, mascot_name=? WHERE id=?",
                   ((request.form.get("slogan") or "").strip()[:80] or None, (request.form.get("mascot_name") or "").strip()[:40] or None, tid))
        audit(db, g.user["username"], "holdindstillinger_gemt", g.team["name"])
        db.commit()
        flash("Holdindstillinger gemt.", "ok")
        return redirect(url_for("team.settings"))
    heads = [r["display_name"] for r in db.execute("SELECT u.display_name FROM team_heads h JOIN users u ON u.id=h.user_id WHERE h.team_id=? ORDER BY u.display_name COLLATE NOCASE", (tid,))]
    return render_template("team_settings.html", ical_url=get_setting(db, tid, "ical_url") or "", prof=profile(db, tid), feats=features.load(db, tid), FEATURES=features.FEATURES, types=formations.GAME_TYPES,
                           heads=heads, n_rounds=len(g.rounds), shares=levelcalc.shares(db, tid),
                           has_mascot_img=bool(db.execute("SELECT 1 FROM team_mascot_img WHERE team_id=?", (tid,)).fetchone()))


# ----------------------------------------------------------------------------- maskotbillede (vises på forældrerapporten)
@bp.route("/mascot-image")
def mascot_image():
    row = get_db().execute("SELECT img FROM team_mascot_img WHERE team_id=?", (team_id(),)).fetchone()
    if not row:
        abort(404)
    return Response(row["img"], mimetype="image/jpeg", headers={"Cache-Control": "private, max-age=300"})


@bp.route("/mascot-image/save", methods=["POST"])
def mascot_image_save():
    _need_config()
    db = get_db()
    f = request.files.get("image")
    try:
        img = photos.process_free(f.read(photos.MAX_UPLOAD + 1) if f else b"")
    except photos.PhotoError as e:
        flash(str(e), "error")
        return redirect(url_for("team.settings"))
    db.execute("INSERT INTO team_mascot_img(team_id,img,updated_at) VALUES(?,?,datetime('now')) "
               "ON CONFLICT(team_id) DO UPDATE SET img=excluded.img, updated_at=excluded.updated_at", (team_id(), img))
    audit(db, g.user["username"], "maskotbillede_gemt", g.team["name"])
    db.commit()
    flash("Maskotbilledet er gemt.", "ok")
    return redirect(url_for("team.settings"))


@bp.route("/mascot-image/delete", methods=["POST"])
def mascot_image_delete():
    _need_config()
    db = get_db()
    db.execute("DELETE FROM team_mascot_img WHERE team_id=?", (team_id(),))
    audit(db, g.user["username"], "maskotbillede_fjernet", g.team["name"])
    db.commit()
    flash("Maskotbilledet er fjernet.", "ok")
    return redirect(url_for("team.settings"))


# ----------------------------------------------------------------------------- noter (delt wiki for trænerne på holdet)
def _note_or_404(db, nid):
    n = db.execute("SELECT * FROM team_notes WHERE id=? AND team_id=?", (nid, team_id())).fetchone()
    if not n:
        abort(404)
    return n


def _note_fields():
    body = (request.form.get("body") or "").strip()[:20000]
    title = (request.form.get("title") or "").strip()[:120]
    day = (request.form.get("note_date") or "").strip()
    try:
        from datetime import date
        day = date.fromisoformat(day).isoformat()
    except ValueError:
        day = _today()
    if not title and body:
        title = body.splitlines()[0][:60]
    return title, day, body


@bp.route("/notes")
def notes():
    db = get_db()
    q = (request.args.get("q") or "").strip()[:80]
    sql = "SELECT id, title, note_date, author, updated_at, updated_by, substr(body,1,160) AS snip FROM team_notes WHERE team_id=?"
    args = [team_id()]
    if q:
        sql += " AND (title LIKE ? ESCAPE '\\' OR body LIKE ? ESCAPE '\\')"
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        args += [like, like]
    rows = db.execute(sql + " ORDER BY note_date DESC, id DESC LIMIT 300", args).fetchall()
    return render_template("team_notes.html", rows=rows, q=q)


@bp.route("/notes/new")
def notes_new():
    return render_template("team_note_form.html", n=None, today=_today())


@bp.route("/notes/add", methods=["POST"])
def notes_add():
    db = get_db()
    title, day, body = _note_fields()
    if not body:
        flash("Skriv en note.", "error")
        return redirect(url_for("team.notes_new"))
    cur = db.execute("INSERT INTO team_notes(team_id,user_id,author,created_at,note_date,title,body) VALUES(?,?,?,datetime('now','localtime'),?,?,?)",
                     (team_id(), g.user["id"], g.user["display_name"], day, title, body))
    db.commit()
    flash("Noten er gemt og kan ses af de andre trænere.", "ok")
    return redirect(url_for("team.note_view", nid=cur.lastrowid))


@bp.route("/notes/<int:nid>")
def note_view(nid):
    return render_template("team_note.html", n=_note_or_404(get_db(), nid))


@bp.route("/notes/<int:nid>/edit", methods=["GET", "POST"])
def note_edit(nid):
    db = get_db()
    n = _note_or_404(db, nid)
    if request.method == "POST":
        title, day, body = _note_fields()
        if not body:
            flash("Noten må ikke være tom.", "error")
            return redirect(url_for("team.note_edit", nid=nid))
        db.execute("UPDATE team_notes SET title=?, note_date=?, body=?, updated_at=datetime('now','localtime'), updated_by=? WHERE id=? AND team_id=?",
                   (title, day, body, g.user["display_name"], nid, team_id()))
        db.commit()
        flash("Noten er opdateret.", "ok")
        if request.headers.get("X-Requested-With") == "fetch":      # «Gem» med JavaScript: bliv i redigeringen (I-09)
            return redirect(url_for("team.note_edit", nid=nid))
        return redirect(url_for("team.note_view", nid=nid))
    return render_template("team_note_form.html", n=n, today=_today())


@bp.route("/notes/<int:nid>/delete", methods=["POST"])
def notes_delete(nid):
    db = get_db()
    n = _note_or_404(db, nid)
    if n["user_id"] != g.user["id"] and not can_configure():
        abort(403)
    db.execute("DELETE FROM team_notes WHERE id=?", (nid,))
    db.commit()
    flash("Noten er slettet.", "ok")
    return redirect(url_for("team.notes"))


# ----------------------------------------------------------------------------- spillerniveau
@bp.route("/levels", methods=["GET", "POST"])
def levels():
    db = get_db()
    players = active_players(db)
    rounds = model.load_rounds(db, team_id())
    calc = levelcalc.calc(db, players, rounds)
    if request.method == "POST":
        n = 0
        for p in players:
            v = request.form.get(f"level_{p['id']}", "")
            v = v if v in model.LEVELS else None
            if v != p["level"]:
                db.execute("UPDATE players SET level=? WHERE id=? AND team_id=?", (v, p["id"], team_id()))
                n += 1
        if n:
            audit(db, g.user["username"], "niveau_gemt", f"{g.team['name']}: {n} spillere")
        db.commit()
        flash("Niveauerne er gemt.", "ok")
        return redirect(url_for("team.levels"))
    counts = {lv: sum(1 for p in players if p["level"] == lv) for lv in model.LEVELS}
    counts["uden"] = sum(1 for p in players if not p["level"])
    ccount = {lv: sum(1 for c in calc.values() if c["level"] == lv) for lv in ("A", "B", "C")}
    return render_template("team_levels.html", players=players, LEVELS=model.LEVELS, counts=counts, calc=calc, ccount=ccount, shares=levelcalc.shares(db, team_id()))


# ----------------------------------------------------------------------------- mascot
def _today():
    return datetime.date.today().isoformat()


@bp.route("/mascot", methods=["GET", "POST"])
def mascot():
    db = get_db()
    tid = team_id()
    players = active_players(db)
    if request.method == "POST":
        pid = int_in(request.form.get("player"), 1, 10 ** 9)
        reason = request.form.get("reason")
        day = (request.form.get("taken_on") or _today()).strip()
        if pid not in {p["id"] for p in players} or reason not in model.MASCOT_REASONS or not model.parse_date(day):
            flash("Vælg spiller, årsag og en gyldig dato.", "error")
        else:
            db.execute("UPDATE mascot_log SET returned_on=? WHERE team_id=? AND returned_on IS NULL", (day, tid))      # mascotten kan kun være ét sted
            db.execute("INSERT INTO mascot_log(team_id,player_id,taken_on,reason,note,created_by) VALUES(?,?,?,?,?,?)",
                       (tid, pid, day, reason, (request.form.get("note") or "").strip()[:300] or None, g.user["display_name"]))
            audit(db, g.user["username"], "mascot_registreret", g.team["name"])
            db.commit()
            flash("Registreret.", "ok")
        return redirect(url_for("team.mascot"))
    rows = db.execute("SELECT m.*, p.name FROM mascot_log m JOIN players p ON p.id=m.player_id WHERE m.team_id=? ORDER BY m.taken_on DESC, m.id DESC LIMIT 200", (tid,)).fetchall()
    now_with = next((r for r in rows if not r["returned_on"]), None)
    return render_template("team_mascot.html", rows=rows, players=players, reasons=model.MASCOT_REASONS, today=_today(), now_with=now_with)


def _own_entry(db, mid):
    row = db.execute("SELECT * FROM mascot_log WHERE id=? AND team_id=?", (mid, team_id())).fetchone()
    if not row:
        abort(404)
    return row


@bp.route("/mascot/<int:mid>/return", methods=["POST"])
def mascot_return(mid):
    db = get_db()
    _own_entry(db, mid)
    db.execute("UPDATE mascot_log SET returned_on=? WHERE id=? AND returned_on IS NULL", (_today(), mid))
    db.commit()
    flash("Mascotten er hjemme igen.", "ok")
    return redirect(url_for("team.mascot"))


@bp.route("/mascot/<int:mid>/delete", methods=["POST"])
def mascot_delete(mid):
    db = get_db()
    _own_entry(db, mid)
    db.execute("DELETE FROM mascot_log WHERE id=?", (mid,))
    db.commit()
    flash("Registreringen er slettet.", "ok")
    return redirect(url_for("team.mascot"))


@bp.route("/mascot/report")
def mascot_report():
    db = get_db()
    tid = team_id()
    since = request.args.get("fra", "").strip()
    since = since if model.parse_date(since) else ""
    sql = "SELECT m.*, p.name FROM mascot_log m JOIN players p ON p.id=m.player_id WHERE m.team_id=?"
    args = [tid]
    if since:
        sql += " AND m.taken_on >= ?"
        args.append(since)
    log = db.execute(sql + " ORDER BY m.taken_on, m.id", args).fetchall()
    per = {}
    for r in log:
        e = per.setdefault(r["player_id"], dict(name=r["name"], n=0, last=None, reasons={}))
        e["n"] += 1
        e["last"] = max(e["last"] or "", r["taken_on"])
        e["reasons"][r["reason"]] = e["reasons"].get(r["reason"], 0) + 1
    rows = sorted(per.values(), key=lambda e: (-e["n"], e["name"].lower()))
    totals = {}
    for r in log:
        totals[r["reason"]] = totals.get(r["reason"], 0) + 1
    never = [p["name"] for p in active_players(db) if p["id"] not in per]
    return render_template("team_mascot_report.html", rows=rows, totals=totals, never=never, since=since, total=len(log), reasons=model.MASCOT_REASONS, log=log)


# ----------------------------------------------------------------------------- sæsonskifte
SEASON_PLAYER_COLS = ("name", "birth_date", "shirt_no", *model.POSITION_FIELDS, "level", "foot", "start_date")


@bp.route("/season", methods=["GET", "POST"])
def season():
    """Opretter et nyt hold til den nye sæson ud fra det aktive: spillere (uden scores, fokus, noter og billeder), trænere og indstillinger."""
    _need_config()
    db = get_db()
    old = g.team
    if request.method == "GET":
        return render_template("team_season.html", suggest=f"{old['name']} {datetime.date.today().year + 1}")
    name = (request.form.get("name") or "").strip()[:80]
    label = (request.form.get("season") or "").strip()[:20]
    if not name or db.execute("SELECT 1 FROM teams WHERE name=? AND club_id IS ?", (name, old["club_id"])).fetchone():
        flash("Vælg et holdnavn, der ikke findes i forvejen.", "error")
        return redirect(url_for("team.season"))
    from .db import create_team
    new = create_team(db, name, label, old["club_id"])
    cols = ",".join(SEASON_PLAYER_COLS)
    n = 0
    if request.form.get("players"):
        for p in db.execute(f"SELECT {cols} FROM players WHERE team_id=? AND active=1 ORDER BY id", (old["id"],)):  # nosec B608 – identifikatorer fra faste lister / kun ?-pladsholdere
            db.execute(f"INSERT INTO players(team_id,{cols},active) VALUES(?,{','.join('?' * len(SEASON_PLAYER_COLS))},1)", (new, *[p[c] for c in SEASON_PLAYER_COLS]))  # nosec B608 – identifikatorer fra faste lister / kun ?-pladsholdere
            n += 1
    if request.form.get("trainers"):
        db.execute("INSERT OR IGNORE INTO user_teams(user_id,team_id) SELECT user_id, ? FROM user_teams WHERE team_id=?", (new, old["id"]))
        db.execute("INSERT OR IGNORE INTO team_heads(team_id,user_id) SELECT ?, user_id FROM team_heads WHERE team_id=?", (new, old["id"]))
    for k in ("game_type", "subs", *[f"feat_{x}" for x in features.KEYS]):
        v = get_setting(db, old["id"], k)
        if v is not None:
            set_setting(db, new, k, v)
    db.execute("UPDATE motivation_categories SET title=(SELECT o.title FROM motivation_categories o WHERE o.team_id=? AND o.cat=motivation_categories.cat) WHERE team_id=?", (old["id"], new))
    db.execute("UPDATE motivation_questions SET text=(SELECT o.text FROM motivation_questions o WHERE o.team_id=? AND o.qidx=motivation_questions.qidx) WHERE team_id=?", (old["id"], new))
    db.execute("UPDATE teams SET slogan=?, mascot_name=? WHERE id=?", (old["slogan"], old["mascot_name"], new))
    if request.form.get("archive"):
        db.execute("UPDATE teams SET archived=1 WHERE id=?", (old["id"],))
    audit(db, g.user["username"], "saesonskifte", f"{old['name']} -> {name} ({n} spillere)")
    db.commit()
    from . import teams as _teams
    _teams.switch(db, g.user, new)
    flash(f"Nyt hold «{name}» er oprettet med {n} spillere. Evalueringer og scores starter forfra; det gamle hold er bevaret.", "ok")
    return redirect(url_for("team.index"))


# ----------------------------------------------------------------------------- farver for score 1–5
@bp.route("/farver", methods=["GET", "POST"])
def colors():
    """Holdets egne farver og forklaringstekster for 1–5 (chef-træner/administrator)."""
    _need_config()
    db = get_db()
    tid = team_id()
    if request.method == "POST":
        if request.form.get("action") == "reset":
            heatcfg.reset(db, tid)
            msg = "Standardfarverne er sat tilbage."
        else:
            err = heatcfg.save(db, tid, [request.form.get(f"color_{n}") for n in range(1, 6)],
                               [request.form.get(f"label_{n}") for n in range(1, 6)], request.form.get("mode", "glide"))
            if err:
                flash(err, "error")
                return redirect(url_for("team.colors"))
            msg = "Farverne er gemt."
        audit(db, g.user["username"], "farver_gemt", g.team["name"])
        db.commit()
        flash(msg, "ok")
        return redirect(url_for("team.colors"))
    return render_template("team_colors.html", cfg=heatcfg.load(db, tid), modes=heatcfg.MODES, defaults=heatcfg.DEFAULT_COLORS,
                           preview=[1 + i * 0.5 for i in range(9)])


# ----------------------------------------------------------------------------- egne kriterietekster
def team_criteria(db, tid):
    return criteria_mod.for_team(db, tid)


@bp.route("/criteria", methods=["GET", "POST"])
def criteria():
    _need_config()
    db = get_db()
    tid = team_id()
    if request.method == "POST":
        n = criteria_mod.save_texts(db, tid, {c["idx"]: request.form.get(f"desc_{c['idx']}") for c in model.CRITERIA})
        audit(db, g.user["username"], "kriterietekster_gemt", f"{g.team['name']}: {n} ændret")
        db.commit()
        flash("Kriterietekster gemt. Tomme felter bruger standardteksten.", "ok")
        return redirect(url_for("team.criteria"))
    return render_template("team_criteria.html", crit=team_criteria(db, tid))


# ----------------------------------------------------------------------------- kalender (iCal)
def _cached_events(db, tid):
    try:
        return json.loads(get_setting(db, tid, "ical_cache") or "[]")
    except ValueError:
        return []


@bp.route("/calendar", methods=["GET", "POST"])
def calendar():
    """Kampe og aktiviteter fra holdets kalenderfeed (fx KampKlar). Hentes kun på knaptryk; afholdte kan oprettes som fremmøde."""
    db = get_db()
    tid = team_id()
    url = get_setting(db, tid, "ical_url") or ""
    today = datetime.date.today()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "refresh":
            try:
                events = ical.parse(ical.fetch(url))
                lo, hi = (today - datetime.timedelta(days=90)).isoformat(), (today + datetime.timedelta(days=180)).isoformat()
                events = [e for e in events if lo <= e["day"] <= hi][:300]
                set_setting(db, tid, "ical_cache", json.dumps(events))
                set_setting(db, tid, "ical_at", datetime.datetime.now().strftime("%d-%m-%Y %H:%M"))
                db.commit()
                flash(f"Kalenderen er hentet: {len(events)} aftaler.", "ok")
            except ical.FeedError as exc:
                flash(str(exc), "error")
        elif action == "import" and features.current().get("devdata", True):
            events = _cached_events(db, tid)
            n = 0
            for raw in request.form.getlist("ev"):
                if not raw.isdigit() or int(raw) >= len(events):
                    continue
                e = events[int(raw)]
                if e["day"] > today.isoformat():
                    continue                                          # kun afholdte
                kind = ical.kind_of(e["summary"])
                if db.execute("SELECT 1 FROM att_events WHERE team_id=? AND day=? AND kind=?", (tid, e["day"], kind)).fetchone():
                    continue
                cur = db.execute("INSERT INTO att_events(team_id,kind,day,note,created_by) VALUES(?,?,?,?,?)", (tid, kind, e["day"], e["summary"][:200] or None, g.user["username"]))
                db.execute("INSERT INTO att_marks(event_id,player_id) SELECT ?, id FROM players WHERE team_id=? AND active=1", (cur.lastrowid, tid))
                n += 1
            db.commit()
            flash(f"{n} registreringer oprettet – afkryds fremmøde under Fremmøde.", "ok")
        return redirect(url_for("team.calendar"))
    events = _cached_events(db, tid)
    have = {(r["day"], r["kind"]) for r in db.execute("SELECT day, kind FROM att_events WHERE team_id=?", (tid,))}
    tdy = today.isoformat()
    upcoming = [dict(e, kind=ical.kind_of(e["summary"])) for e in events if e["day"] >= tdy][:15]
    past = [dict(e, i=i, kind=ical.kind_of(e["summary"])) for i, e in enumerate(events) if e["day"] < tdy]
    past = [e for e in reversed(past) if (e["day"], e["kind"]) not in have][:30]
    return render_template("team_calendar.html", url=url, upcoming=upcoming, past=past, at=get_setting(db, tid, "ical_at") or "")
