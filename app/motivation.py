"""Motivation og træningsønsker: spørgsmål (3 kategorier, 22 pladser), input pr. spiller, tablet-visning og rapport."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from . import model
from .db import get_db
from .helpers import active_players, get_player, int_in, neighbours, team_id

bp = Blueprint("motivation", __name__, url_prefix="/motivation")


def load_questions(db):
    tid = team_id()
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
    return render_template("motivation_report.html", p=p, data=data)
