"""Serverside SVG-diagrammer (ingen JavaScript, ingen eksterne biblioteker – virker offline og i print)."""
import math

from markupsafe import Markup, escape

COLORS = ["#1f4e79", "#e07b00", "#2e8b57", "#9b59b6"]


HEAT_STOPS = ((1, (0xF8, 0x69, 0x6B)),     # standard: 1 rød
              (2, (0xFF, 0xEB, 0x84)),     # 2 gul
              (3, (0x63, 0xBE, 0x7B)),     # 3 grøn = målet (på niveau med årgangen)
              (4, (0xE0, 0xB0, 0x20)),     # 4 mørkere gul
              (5, (0x9D, 0xC3, 0xE6)))     # 5 lysere blå = bedre end årgangen. Holdet kan vælge egne farver (heatcfg.py).


def heat(v, lo=1.0, mid=3.0, hi=5.0):
    """Farve for en score 1–5 efter holdets farver: glidende mellem tallene eller faste blokke (afrundet)."""
    if v is None:
        return "#f2f2f2"
    from . import heatcfg
    heatcfg.mark_used()
    cfg = heatcfg.current()
    x = 1 + 4 * (max(lo, min(hi, v)) - lo) / (hi - lo)
    if cfg["mode"] == "blok":
        return cfg["colors"][min(4, max(0, int(x + 0.5) - 1))]
    stops = [(n + 1, heatcfg.rgb(c)) for n, c in enumerate(cfg["colors"])]
    for (x0, a), (x1, b) in zip(stops, stops[1:]):
        if x <= x1:
            t = (x - x0) / (x1 - x0)
            return "#%02x%02x%02x" % tuple(round(a[k] + (b[k] - a[k]) * t) for k in range(3))
    return cfg["colors"][-1]


def heat_fg(v):
    """Tekstfarve, der kan læses på heat(v)."""
    from . import heatcfg
    return "#1b1b1b" if v is None else heatcfg.text_color(heat(v))


def _svg(w, h, body, label):
    return Markup(f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(label)}" '  # nosec B704 – server-genereret SVG/QR, værdier escapet
                  f'xmlns="http://www.w3.org/2000/svg">{body}</svg>')


def radar(labels, series, vmax=5, label="Radardiagram"):
    """series: [(navn, [værdier], farve)]. None tegnes som 0."""
    w, h = 440, 360
    cx, cy = 220, 180
    r = 108
    n = len(labels)
    ang = lambda i: -math.pi / 2 + 2 * math.pi * i / n
    pt = lambda i, v: (cx + r * (v / vmax) * math.cos(ang(i)), cy + r * (v / vmax) * math.sin(ang(i)))
    out = []
    for ring in range(1, vmax + 1):
        pts = " ".join("%.1f,%.1f" % pt(i, ring) for i in range(n))
        out.append(f'<polygon points="{pts}" fill="none" stroke="#d0d7de" stroke-width="1"/>')
        x, y = pt(0, ring)
        out.append(f'<text x="{x + 3:.1f}" y="{y:.1f}" font-size="9" fill="#888">{ring}</text>')
    for i, lab in enumerate(labels):
        x, y = pt(i, vmax)
        out.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#d0d7de"/>')
        lx, ly = cx + (r + 22) * math.cos(ang(i)), cy + (r + 22) * math.sin(ang(i))
        anchor = "middle" if abs(math.cos(ang(i))) < 0.3 else ("start" if math.cos(ang(i)) > 0 else "end")
        out.append(f'<text x="{lx:.1f}" y="{ly + 4:.1f}" font-size="12" text-anchor="{anchor}" fill="#222">{escape(lab)}</text>')
    for k, (name, vals, color) in enumerate(series):
        pts = " ".join("%.1f,%.1f" % pt(i, v or 0) for i, v in enumerate(vals))
        out.append(f'<polygon points="{pts}" fill="{color}" fill-opacity="0.18" stroke="{color}" stroke-width="2.2"/>')
        for i, v in enumerate(vals):
            if v is not None:
                x, y = pt(i, v)
                out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{color}"><title>{escape(labels[i])}: {v:.1f}</title></circle>')
    for k, (name, _v, color) in enumerate(series):
        out.append(f'<rect x="10" y="{h - 14 - 16 * (len(series) - 1 - k)}" width="10" height="10" fill="{color}"/>'
                   f'<text x="25" y="{h - 5 - 16 * (len(series) - 1 - k)}" font-size="11">{escape(name)}</text>')
    return _svg(w, h, "".join(out), label)


def line_chart(x_labels, series, ymin=1, ymax=5, label="Udvikling"):
    """series: [(navn, [værdier/None], farve)] – None giver et hul i linjen."""
    w, h, ml, mr, mt, mb = 560, 290, 38, 16, 16, 58
    pw, ph = w - ml - mr, h - mt - mb
    n = len(x_labels)
    X = lambda i: ml + (pw * i / (n - 1) if n > 1 else pw / 2)
    Y = lambda v: mt + ph * (1 - (v - ymin) / (ymax - ymin))
    out = []
    for v in range(int(ymin), int(ymax) + 1):
        out.append(f'<line x1="{ml}" y1="{Y(v):.1f}" x2="{w - mr}" y2="{Y(v):.1f}" stroke="#e3e8ee"/>'
                   f'<text x="{ml - 6}" y="{Y(v) + 4:.1f}" font-size="11" text-anchor="end" fill="#666">{v}</text>')
    for i, lab in enumerate(x_labels):
        out.append(f'<text x="{X(i):.1f}" y="{h - mb + 16}" font-size="11" text-anchor="middle" fill="#444">{escape(lab)}</text>')
    for k, (name, vals, color) in enumerate(series):
        seg = []
        for i, v in enumerate(list(vals) + [None]):
            if v is not None:
                seg.append("%.1f,%.1f" % (X(i), Y(v)))
            elif seg:
                if len(seg) > 1:
                    out.append(f'<polyline points="{" ".join(seg)}" fill="none" stroke="{color}" stroke-width="2.4"/>')
                seg = []
        for i, v in enumerate(vals):
            if v is not None:
                out.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="3.6" fill="{color}"><title>{escape(name)}: {v:.1f}</title></circle>')
        lx = ml + (k % 4) * 135
        ly = h - 22 + 14 * (k // 4)
        out.append(f'<rect x="{lx}" y="{ly - 9}" width="10" height="10" fill="{color}"/>'
                   f'<text x="{lx + 14}" y="{ly}" font-size="11">{escape(name)}</text>')
    return _svg(w, h, "".join(out), label)


def bars(items, vmax=5, label="Søjlediagram"):
    """items: [(navn, værdi/None)] – vandrette søjler."""
    row, w, ml = 26, 560, 150
    h = row * len(items) + 8
    out = []
    for i, (name, v) in enumerate(items):
        y = 4 + i * row
        out.append(f'<text x="{ml - 8}" y="{y + 16}" font-size="12" text-anchor="end">{escape(name)}</text>')
        if v is not None:
            bw = (w - ml - 50) * v / vmax
            out.append(f'<rect x="{ml}" y="{y + 3}" width="{bw:.1f}" height="16" rx="3" fill="{heat(v)}" stroke="#9aa5b1"/>'
                       f'<text x="{ml + bw + 6:.1f}" y="{y + 16}" font-size="12">{v:.1f}'.replace(".", ",") + "</text>")
    return _svg(w, h, "".join(out), label)


# Banevisning: position -> (y i % fra modstanderens mål, bane). Bane: L/C/R = venstre/midt/højre bane, B = begge sider (fordeles).
_POS_XY = {"Målmand": (90, "C"), "Forsvar": (72, "C"), "Højre back": (72, "R"), "Venstre back": (72, "L"), "Midtstopper": (76, "C"),
           "Defensiv midtbane": (60, "C"), "Midtbane": (47, "C"), "Offensiv midtbane": (36, "C"),
           "Kant": (30, "B"), "Højre kant": (30, "R"), "Venstre kant": (30, "L"), "Angreb": (13, "C"), "Allround": (56, "C")}
_LANE = {"L": (30, 140), "C": (150, 250), "R": (260, 370)}


def _field(w, h, boxes=True):
    out = [f'<rect x="4" y="4" width="{w - 8}" height="{h - 8}" rx="8" fill="#3a9a55" stroke="#fff" stroke-width="3"/>',
           f'<line x1="4" y1="{h / 2}" x2="{w - 4}" y2="{h / 2}" stroke="#fff" stroke-width="2"/>',
           f'<circle cx="{w / 2}" cy="{h / 2}" r="46" fill="none" stroke="#fff" stroke-width="2"/>']
    if boxes:
        out += [f'<rect x="110" y="4" width="180" height="70" fill="none" stroke="#fff" stroke-width="2"/>',
                f'<rect x="110" y="{h - 74}" width="180" height="70" fill="none" stroke="#fff" stroke-width="2"/>']
    return out


def _spread(n, lo, hi):
    return [(lo + hi) / 2] if n == 1 else [lo + (hi - lo) * i / (n - 1) for i in range(n)]


def pitch(players, label="Bane"):
    """players: [{name, position, value, photo?, pid?}] – placeres efter position (venstre/midt/højre) og farves efter score.
    Med `photo` (URL) vises et mini-billede i en cirkel med scorefarvet ring."""
    w, h = 400, 560
    out = _field(w, h)
    cells = {}
    for p in players:
        y, lane = _POS_XY.get(p["position"], _POS_XY["Allround"])
        cells.setdefault((y, lane), []).append(p)
    for (y, lane), plist in cells.items():
        if lane == "B":                                             # «Kant»: begge sider – skiftevis venstre og højre
            for side, items in (("L", plist[0::2]), ("R", plist[1::2])):
                _row(out, items, y, h, *_LANE[side])
        else:
            _row(out, plist, y, h, *_LANE[lane], wide=len(plist) > 3)
    return _svg(w, h, "".join(out), label)


def _row(out, items, y, h, lo, hi, wide=False):
    if not items:
        return
    if wide:
        lo, hi = 40, 360
    xs = _spread(len(items), lo, hi)
    for i, (x, p) in enumerate(zip(xs, items)):
        _dot(out, x, h * y / 100 + (14 if wide and i % 2 else 0), p)


def formation_pitch(game_type, placed, label="Opstilling"):
    """placed: [{x, y, tag, player: {name, value, photo?, pid?} | None}] i procent (se formations.slots)."""
    w, h = 400, 560
    out = _field(w, h, boxes=game_type != "3v3")
    for s in placed:
        x, y = w * s["x"] / 100, h * s["y"] / 100
        if s["player"]:
            _dot(out, x, y, s["player"])
        else:
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="17" fill="none" stroke="#fff" stroke-width="2" stroke-dasharray="4 3" opacity=".85"/>'
                       f'<text x="{x:.1f}" y="{y + 31:.1f}" font-size="9" text-anchor="middle" fill="#fff">{escape(s["tag"])}</text>')
    return _svg(w, h, "".join(out), label)


def _dot(out, x, y, p):
    v = p.get("value")
    first = (p["name"] or "?").split()
    short = first[0] + (" " + first[-1][0] + "." if len(first) > 1 else "")
    score = "%.1f" % v if v is not None else "–"
    title = f'<title>{escape(p["name"])} – {"%.1f" % v if v is not None else "ingen score"}</title>'
    if p.get("photo"):
        cid = f'cp{p.get("pid", 0)}_{int(x)}_{int(y)}'
        out.append(f'<clipPath id="{cid}"><circle cx="{x:.1f}" cy="{y:.1f}" r="16"/></clipPath>'
                   f'<circle cx="{x:.1f}" cy="{y:.1f}" r="19" fill="{heat(v)}" stroke="#fff" stroke-width="2">{title}</circle>'
                   f'<image href="{escape(p["photo"])}" x="{x - 16:.1f}" y="{y - 16:.1f}" width="32" height="32" clip-path="url(#{cid})" '
                   f'preserveAspectRatio="xMidYMid slice"/>'
                   f'<circle cx="{x + 14:.1f}" cy="{y + 14:.1f}" r="9" fill="{heat(v)}" stroke="#fff" stroke-width="1.5"/>'
                   f'<text x="{x + 14:.1f}" y="{y + 17.5:.1f}" font-size="9" text-anchor="middle" font-weight="700">{score}</text>'
                   f'<text x="{x:.1f}" y="{y + 33:.1f}" font-size="10" text-anchor="middle" fill="#fff" font-weight="600">{escape(short)}</text>')
        return
    out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="15" fill="{heat(v)}" stroke="#fff" stroke-width="2">{title}</circle>'
               f'<text x="{x:.1f}" y="{y + 4:.1f}" font-size="10" text-anchor="middle" font-weight="700">{score}</text>'
               f'<text x="{x:.1f}" y="{y + 29:.1f}" font-size="10" text-anchor="middle" fill="#fff" font-weight="600">{escape(short)}</text>')
