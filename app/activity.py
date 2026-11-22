"""Brugsstatistik: hvem er aktive nu, og hvornår på dagen bruges systemet (15 minutters opløsning).

Der gemmes kun *at* en bruger var aktiv i et kvarter (bruger, kvarter, hold) og tidspunktet for sidste aktivitet.
Ingen sider, ingen indhold, ingen IP-adresser, ingen scores. Kvartererne slettes efter 180 dage (db.purge_old).
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import current_app, g, request, session
from markupsafe import Markup

SLOT = 900                    # 15 minutter
ONLINE_WINDOW = 300           # «aktiv nu» = set inden for 5 minutter
SKIP_ENDPOINTS = {"static", "healthz", "main.club_logo", "players.photo_view"}
DAYS = ["Man", "Tir", "Ons", "Tor", "Fre", "Lør", "Søn"]


def tz():
    try:
        return ZoneInfo(current_app.config.get("TIMEZONE") or "Europe/Copenhagen")
    except Exception:         # noqa: BLE001 – ukendt zone → UTC frem for at gå ned
        return ZoneInfo("UTC")


def record(db, user_id, team_id, now=None):
    now = int(now if now is not None else time.time())
    db.execute("INSERT OR IGNORE INTO activity(user_id, slot, team_id) VALUES(?,?,?)", (user_id, now // SLOT, team_id))
    db.execute("INSERT INTO presence(user_id, last_seen, team_id) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
               "last_seen=excluded.last_seen, team_id=excluded.team_id WHERE presence.last_seen < excluded.last_seen - 30 "
               "OR presence.team_id IS NOT excluded.team_id", (user_id, now, team_id))
    db.commit()


def touch():
    """before_request (efter login-kontrol): registrér aktivitet for fuldt indloggede brugere (ikke 'se som', ikke statiske filer)."""
    try:
        if (g.get("user") and session.get("stage") == "ok" and not g.get("viewing") and request.endpoint
                and request.endpoint not in SKIP_ENDPOINTS):
            from .db import get_db
            record(get_db(), g.user["id"], g.team["id"] if g.get("team") else None)
    except Exception:         # noqa: BLE001 – statistik må aldrig vælte en side
        current_app.logger.warning("Aktivitet kunne ikke registreres", exc_info=True)


def badge():
    """Til headeren: {team: [...], total: [...]|None}; None hvis ikke fuldt indlogget. Cachet pr. request."""
    if not g.get("user") or session.get("stage") != "ok":
        return None
    if "online_badge" not in g:
        from .db import get_db
        g.online_badge = summary(get_db(), g.user, g.get("team"))
    return g.online_badge


def online(db, team_id=None, everyone=False, now=None):
    """Aktive brugere (seneste 5 min). `team_id`: kun det hold. `everyone`: alle hold (kun til administratorer)."""
    now = int(now if now is not None else time.time())
    sql = ("SELECT u.id, u.display_name, u.role, p.last_seen, p.team_id, t.name AS team FROM presence p "
           "JOIN users u ON u.id=p.user_id LEFT JOIN teams t ON t.id=p.team_id WHERE p.last_seen >= ? ")
    args = [now - ONLINE_WINDOW]
    if not everyone:
        sql += "AND p.team_id = ? "
        args.append(team_id)
    return db.execute(sql + "ORDER BY u.display_name COLLATE NOCASE", args).fetchall()


def summary(db, user, team):
    """Til forsiden: aktive på mit hold (+ i alt for administratorer)."""
    out = dict(window=ONLINE_WINDOW // 60, team=online(db, team["id"]) if team else [], total=None)
    if user["role"] == "admin":
        out["total"] = online(db, everyone=True)
    return out


def usage(db, days=30, team_id=None, now=None):
    """Aktive brugerkvarterer pr. kvarter på døgnet (96) og pr. ugedag×kvarter, i lokal tid."""
    now = int(now if now is not None else time.time())
    since = now // SLOT - days * 96
    sql, args = "SELECT slot, COUNT(*) n, COUNT(DISTINCT user_id) u FROM activity WHERE slot >= ? ", [since]
    if team_id:
        sql += "AND team_id = ? "
        args.append(team_id)
    zone = tz()
    by_day = [0] * 96
    grid = [[0] * 96 for _ in range(7)]
    total = 0
    for r in db.execute(sql + "GROUP BY slot", args):
        local = datetime.fromtimestamp(r["slot"] * SLOT, zone)
        k = local.hour * 4 + local.minute // 15
        by_day[k] += r["n"]
        grid[local.weekday()][k] += r["n"]
        total += r["n"]
    top = sorted(((v, d, k) for d, row in enumerate(grid) for k, v in enumerate(row) if v), reverse=True)[:10]
    return dict(by_day=by_day, grid=grid, total=total, days=days, top=top)


def label(k):
    return "%02d:%02d" % divmod(k * 15, 60)


def users_table(db, days=30, team_id=None, now=None):
    now = int(now if now is not None else time.time())
    since = now // SLOT - days * 96
    sql = ("SELECT u.display_name, u.username, u.role, p.last_seen, COUNT(a.slot) AS slots FROM users u "
           "LEFT JOIN presence p ON p.user_id=u.id LEFT JOIN activity a ON a.user_id=u.id AND a.slot >= ? ")
    sql_where = "WHERE u.stopped_at IS NULL "
    args = [since]
    if team_id:
        sql += "AND a.team_id = ? "
        args.append(team_id)
    rows = db.execute(sql + sql_where + "GROUP BY u.id ORDER BY p.last_seen DESC, u.display_name COLLATE NOCASE", args).fetchall()
    zone = tz()
    return [dict(r, seen=datetime.fromtimestamp(r["last_seen"], zone).strftime("%d-%m-%Y %H:%M") if r["last_seen"] else "")
            for r in rows]


# ------------------------------------------------------------------ diagrammer (server-SVG, ingen JavaScript)
def bar_chart(values):
    """96 søjler (ét pr. kvarter) med timeakse."""
    w, h, left, bottom = 480, 170, 24, 22
    mx = max(values) or 1
    bw = (w - left - 4) / 96
    body = [f'<line x1="{left}" y1="{h - bottom}" x2="{w - 4}" y2="{h - bottom}" stroke="#999"/>']
    for k, v in enumerate(values):
        if v:
            bh = (h - bottom - 12) * v / mx
            body.append(f'<rect x="{left + k * bw:.1f}" y="{h - bottom - bh:.1f}" width="{max(bw - .4, .6):.1f}" height="{bh:.1f}" fill="#1f4e79">'
                        f'<title>{label(k)}–{label((k + 1) % 96)}: {v}</title></rect>')
    for hr in range(0, 24, 3):
        x = left + hr * 4 * bw
        body.append(f'<text x="{x:.1f}" y="{h - 7}" font-size="9" fill="#555" text-anchor="middle">{hr:02d}</text>')
    body.append(f'<text x="2" y="10" font-size="9" fill="#555">{mx}</text>')
    return Markup(f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="Brug pr. kvarter" xmlns="http://www.w3.org/2000/svg">{"".join(body)}</svg>')  # nosec B704 – server-genereret SVG/QR, værdier escapet


def heatmap(grid):
    """7 ugedage × 96 kvarterer."""
    w, left, top, ch = 480, 26, 4, 16
    h = top + 7 * ch + 16
    cw = (w - left - 4) / 96
    mx = max((v for row in grid for v in row), default=0) or 1
    body = []
    for d, row in enumerate(grid):
        body.append(f'<text x="2" y="{top + d * ch + 11}" font-size="9" fill="#555">{DAYS[d]}</text>')
        for k, v in enumerate(row):
            if v:
                op = .15 + .85 * v / mx
                body.append(f'<rect x="{left + k * cw:.1f}" y="{top + d * ch}" width="{cw + .2:.1f}" height="{ch - 1}" fill="#1f4e79" fill-opacity="{op:.2f}">'
                            f'<title>{DAYS[d]} {label(k)}: {v}</title></rect>')
    for hr in range(0, 24, 3):
        body.append(f'<text x="{left + hr * 4 * cw:.1f}" y="{h - 3}" font-size="9" fill="#555" text-anchor="middle">{hr:02d}</text>')
    return Markup(f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="Brug pr. ugedag og kvarter" xmlns="http://www.w3.org/2000/svg">{"".join(body)}</svg>')  # nosec B704 – server-genereret SVG/QR, værdier escapet
