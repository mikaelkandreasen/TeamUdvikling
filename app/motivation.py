"""Motivation og træningsønsker: spørgsmål (3 kategorier, 22 pladser), input pr. spiller, tablet-visning og rapport."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from . import model
from .db import get_db
from .helpers import active_players, get_player, int_in, neighbours, team_id

bp = Blueprint("motivation", __name__, url_prefix="/motivation")


def load_questions(db, tid=None):
    tid = tid or team_id()
    cats = {r["cat"]: r["title"] for r in db.execute("SELECT cat, title FROM motivation_categories WHERE team_id=?", (tid,))}
    qs = db.execute("SELECT qidx, cat, text FROM motivation_questions WHERE team_id=? ORDER BY qidx", (tid,)).fetchall()
    return cats, [dict(q) for q in qs]


def load_answers(db):
    out = {}
    for r in db.execute("SELECT a.player_id, a.qidx, a.score FROM motivation_answers a JOIN players p ON p.id=a.player_id WHERE p.team_id=?", (team_id(),)):
        out.setdefault(r["player_id"], {})[r["qidx"]] = r["score"]
    return out


def report_data(db, pid, player_ids):
    cats, qs = load_questions(db)
    ans = load_answers(db)
    mine = ans.get(pid, {})
    out = []
    for cat in sorted(cats):
        rows = []
        for q in (x for x in qs if x["cat"] == cat and x["text"].strip()):
            hold = model.mean([ans.get(p, {}).get(q["qidx"]) for p in player_ids])
            v = mine.get(q["qidx"])
            rows.append(dict(text=q["text"], score=v, hold=hold, diff=(v - hold) if v is not None and hold is not None else None))
        if not rows:
            continue
        mv = model.mean([r["score"] for r in rows])
        hv = model.mean([r["hold"] for r in rows])
        top = max((r for r in rows if r["score"] is not None), key=lambda r: r["score"], default=None)
        out.append(dict(cat=cat, title=cats[cat], rows=rows, avg=mv, hold_avg=hv,
                        diff=(mv - hv) if mv is not None and hv is not None else None, top=top["text"] if top else None))
    return out


def history(db, pid):
    """Motivation over tid: [{date, cats: {cat_titel: gennemsnit}}] – kun datoer hvor spilleren har svaret. Vises når der er mindst to målinger."""
    cats, qs = load_questions(db)
    qcat = {q["qidx"]: q["cat"] for q in qs if q["text"].strip()}
    by = {}
    for r in db.execute("SELECT qidx, score, taken_on FROM motivation_log WHERE player_id=? ORDER BY taken_on", (pid,)):
        if r["qidx"] in qcat:
            by.setdefault(r["taken_on"], {}).setdefault(qcat[r["qidx"]], []).append(r["score"])
    titles = [(c, cats[c]) for c in sorted(cats)]
    rows = [dict(date=d, vals=[model.mean(v.get(c)) if v.get(c) else None for c, _ in titles]) for d, v in sorted(by.items())]
    return dict(titles=[t for _, t in titles], rows=rows) if len(rows) >= 2 else None


@bp.route("/", methods=["GET", "POST"])
def matrix():
    db = get_db()
    cats, qs = load_questions(db)
    visible = [q for q in qs if q["text"].strip()]
    players = active_players(db)
    if request.method == "POST":
        for p in players:
            for q in visible:
                v = int_in(request.form.get(f"a_{p['id']}_{q['qidx']}"), 1, 5)
                if v:
                    db.execute("INSERT INTO motivation_answers(player_id,qidx,score) VALUES(?,?,?) "
                               "ON CONFLICT(player_id,qidx) DO UPDATE SET score=excluded.score", (p["id"], q["qidx"], v))
                else:
                    db.execute("DELETE FROM motivation_answers WHERE player_id=? AND qidx=?", (p["id"], q["qidx"]))
        db.commit()
        flash("Svar gemt.", "ok")
        return redirect(url_for("motivation.matrix"))
    ans = load_answers(db)
    col_avg = {q["qidx"]: model.mean([ans.get(p["id"], {}).get(q["qidx"]) for p in players]) for q in visible}
    cat_avg = {p["id"]: {c: model.mean([ans.get(p["id"], {}).get(q["qidx"]) for q in visible if q["cat"] == c]) for c in cats} for p in players}
    return render_template("motivation_matrix.html", cats=cats, visible=visible, players=players, ans=ans, col_avg=col_avg, cat_avg=cat_avg)


@bp.route("/questions", methods=["GET", "POST"])
def questions():
    db = get_db()
    if request.method == "POST":
        for cat in range(len(model.CAT_SIZES)):
            title = (request.form.get(f"title_{cat}") or "").strip()[:120] or f"Kategori {cat + 1}"
            db.execute("UPDATE motivation_categories SET title=? WHERE cat=? AND team_id=?", (title, cat, team_id()))
        for q in range(model.N_Q):
            db.execute("UPDATE motivation_questions SET text=? WHERE qidx=? AND team_id=?", ((request.form.get(f"q_{q}") or "").strip()[:250], q, team_id()))
        db.commit()
        flash("Spørgsmål gemt.", "ok")
        return redirect(url_for("motivation.questions"))
    cats, qs = load_questions(db)
    return render_template("motivation_questions.html", cats=cats, qs=qs)


@bp.route("/tablet")
def tablet_list():
    return render_template("motivation_tablet_list.html", players=active_players(get_db()))


@bp.route("/tablet/<int:pid>", methods=["GET", "POST"])
def tablet(pid):
    db = get_db()
    p = get_player(db, pid)
    cats, qs = load_questions(db)
    visible = [q for q in qs if q["text"].strip()]
    if request.method == "POST":
        for q in visible:
            v = int_in(request.form.get(f"q{q['qidx']}"), 1, 5)
            if v:
                db.execute("INSERT INTO motivation_answers(player_id,qidx,score) VALUES(?,?,?) "
                           "ON CONFLICT(player_id,qidx) DO UPDATE SET score=excluded.score", (pid, q["qidx"], v))
        db.commit()
        flash("Tak for dine svar!", "ok")
        return redirect(url_for("motivation.tablet_list"))
    mine = load_answers(db).get(pid, {})
    return render_template("motivation_tablet.html", p=p, cats=cats, visible=visible, mine=mine)


@bp.route("/report/<int:pid>")
def report(pid):
    db = get_db()
    p = get_player(db, pid)
    data = report_data(db, pid, [x["id"] for x in active_players(db)])
    return render_template("motivation_report.html", p=p, data=data, over_tid=history(db, pid))


# ----------------------------------------------------------------------------- spillerlink (engangslink til motivationsskemaet)
import hashlib
import hmac
import secrets
import time

from flask import current_app, g

from . import features, mailer
from .auth import _too_many, record_fail, throttled

LINK_TTL = 7 * 86400
public_bp = Blueprint("playerlink", __name__)


def _lh(token):
    return hmac.new(current_app.config["SECRET_KEY"].encode(), (token or "").encode(), hashlib.sha256).hexdigest()


def link_status(row, now=None):
    now = int(now if now is not None else time.time())
    if row["used_at"]:
        return "besvaret"
    if row["revoked"]:
        return "tilbagekaldt"
    return "udløbet" if row["expires_at"] <= now else "afventer"


def _qr(url):
    from .auth import _qr_svg
    return _qr_svg(url)


@bp.route("/links", methods=["GET", "POST"])
def links():
    """Trænere opretter et engangslink pr. spiller. Linket vises kun lige efter oprettelsen (kun hashen gemmes)."""
    db = get_db()
    players = active_players(db)
    new = None
    if request.method == "POST":
        pid = int_in(request.form.get("player"), 1, 10 ** 9)
        p = next((x for x in players if x["id"] == pid), None)
        if not p:
            abort(404)
        db.execute("UPDATE player_links SET revoked=1 WHERE player_id=? AND used_at IS NULL AND revoked=0", (pid,))
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        db.execute("INSERT INTO player_links(player_id,token_hash,created_at,expires_at,created_by) VALUES(?,?,?,?,?)",
                   (pid, _lh(token), now, now + LINK_TTL, g.user["username"]))
        from .db import audit
        audit(db, g.user["username"], "spillerlink_oprettet", f"spiller {pid}")
        db.commit()
        base = mailer.public_url() or request.host_url.rstrip("/")
        url = f"{base}/svar/{token}"
        new = dict(name=p["name"], url=url, qr=_qr(url))
    rows = db.execute("SELECT l.*, p.name FROM player_links l JOIN players p ON p.id=l.player_id WHERE p.team_id=? ORDER BY l.created_at DESC LIMIT 100", (team_id(),)).fetchall()
    return render_template("motivation_links.html", players=players, rows=[dict(r, state=link_status(r)) for r in rows], new=new)


@bp.route("/links/<int:lid>/revoke", methods=["POST"])
def link_revoke(lid):
    db = get_db()
    row = db.execute("SELECT l.id FROM player_links l JOIN players p ON p.id=l.player_id WHERE l.id=? AND p.team_id=?", (lid, team_id())).fetchone()
    if not row:
        abort(404)
    db.execute("UPDATE player_links SET revoked=1 WHERE id=? AND used_at IS NULL", (lid,))
    db.commit()
    flash("Linket er tilbagekaldt.", "ok")
    return redirect(url_for("motivation.links"))


def _valid_link(db, token):
    if not token or len(token) > 100:
        return None
    return db.execute("SELECT l.*, p.name AS pname, p.team_id FROM player_links l JOIN players p ON p.id=l.player_id "
                      "WHERE l.token_hash=? AND l.used_at IS NULL AND l.revoked=0 AND l.expires_at>? AND p.active=1",
                      (_lh(token), int(time.time()))).fetchone()


@public_bp.route("/svar/<token>", methods=["GET", "POST"])
def form(token):
    """Offentlig side uden login: kun dette ene skema til denne ene spiller, én gang. GET forbruger ikke linket (mailscannere)."""
    db = get_db()
    if throttled(db):
        return _too_many()
    row = _valid_link(db, token)
    if row and not features.load(db, row["team_id"]).get("motivation", True):
        row = None
    if not row:
        record_fail(db)
        return render_template("player_link_invalid.html"), 400
    cats, qs = load_questions(db, row["team_id"])
    visible = [q for q in qs if q["text"].strip()]
    if request.method == "POST":
        answers = {q["qidx"]: int_in(request.form.get(f"q{q['qidx']}"), 1, 5) for q in visible}
        answers = {k: v for k, v in answers.items() if v}
        if not answers:
            flash("Tryk på mindst ét tal.", "error")
        else:
            used = db.execute("UPDATE player_links SET used_at=? WHERE id=? AND used_at IS NULL AND revoked=0 AND expires_at>?",
                              (int(time.time()), row["id"], int(time.time())))
            if used.rowcount != 1:                 # en anden anmodning nåede først
                db.rollback()
                return render_template("player_link_invalid.html"), 400
            for qidx, v in answers.items():
                db.execute("INSERT INTO motivation_answers(player_id,qidx,score) VALUES(?,?,?) "
                           "ON CONFLICT(player_id,qidx) DO UPDATE SET score=excluded.score", (row["player_id"], qidx, v))
            db.commit()
            return render_template("player_link_done.html")
    return render_template("motivation_tablet.html", p=dict(name=row["pname"]), cats=cats, visible=visible, mine={}, public=True)
