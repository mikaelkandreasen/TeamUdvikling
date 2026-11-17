"""Serverside SVG-diagrammer (ingen JavaScript, ingen eksterne biblioteker – virker offline og i print)."""
import math

from markupsafe import Markup, escape

COLORS = ["#1f4e79", "#e07b00", "#2e8b57", "#9b59b6"]


def heat(v, lo=1.0, mid=3.0, hi=5.0):
    """Rød–gul–grøn farve for en score."""
    if v is None:
        return "#f2f2f2"
    v = max(lo, min(hi, v))
    a, b, t = ((0xF8, 0x69, 0x6B), (0xFF, 0xEB, 0x84), (v - lo) / (mid - lo)) if v <= mid else \
              ((0xFF, 0xEB, 0x84), (0x63, 0xBE, 0x7B), (v - mid) / (hi - mid))
    c = [round(a[i] + (b[i] - a[i]) * t) for i in range(3)] if v <= mid else \
        [round(a[i] + ((0x63, 0xBE, 0x7B)[i] - a[i]) * t) for i in range(3)]
    return "#%02x%02x%02x" % tuple(c)


def _svg(w, h, body, label):
    return Markup(f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(label)}" '
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


# Banevisning: position -> (x%, y%) for vandret placering fordeles automatisk
_PITCH_Y = {"Målmand": 90, "Forsvar": 72, "Allround": 56, "Midtbane": 47, "Kant": 30, "Angreb": 13}


def pitch(players, label="Bane"):
    """players: [{name, position, value}] – placeres efter position og farves efter score."""
    w, h = 400, 560
    out = [f'<rect x="4" y="4" width="{w - 8}" height="{h - 8}" rx="8" fill="#3a9a55" stroke="#fff" stroke-width="3"/>',
           f'<line x1="4" y1="{h / 2}" x2="{w - 4}" y2="{h / 2}" stroke="#fff" stroke-width="2"/>',
           f'<circle cx="{w / 2}" cy="{h / 2}" r="46" fill="none" stroke="#fff" stroke-width="2"/>',
           f'<rect x="110" y="4" width="180" height="70" fill="none" stroke="#fff" stroke-width="2"/>',
           f'<rect x="110" y="{h - 74}" width="180" height="70" fill="none" stroke="#fff" stroke-width="2"/>']
    groups = {}
    for p in players:
        groups.setdefault(p["position"] if p["position"] in _PITCH_Y else "Allround", []).append(p)
    for pos, plist in groups.items():
        if pos == "Kant":
            lines = [plist[0::2], plist[1::2]]
            xs = [lambda i, n: 60 + 40 * i, lambda i, n: w - 60 - 40 * i]
            for side, items in enumerate(lines):
                for i, p in enumerate(items):
                    _dot(out, xs[side](i, len(items)), h * _PITCH_Y[pos] / 100, p)
            continue
        n = len(plist)
        for i, p in enumerate(plist):
            _dot(out, w * (i + 1) / (n + 1), h * _PITCH_Y[pos] / 100, p)
    return _svg(w, h, "".join(out), label)


def _dot(out, x, y, p):
    v = p.get("value")
    first = (p["name"] or "?").split()
    short = first[0] + (" " + first[-1][0] + "." if len(first) > 1 else "")
    out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="15" fill="{heat(v)}" stroke="#fff" stroke-width="2">'
               f'<title>{escape(p["name"])} – {"%.1f" % v if v is not None else "ingen score"}</title></circle>'
               f'<text x="{x:.1f}" y="{y + 4:.1f}" font-size="10" text-anchor="middle" font-weight="700">'
               f'{"%.1f" % v if v is not None else "–"}</text>'
               f'<text x="{x:.1f}" y="{y + 29:.1f}" font-size="10" text-anchor="middle" fill="#fff" font-weight="600">{escape(short)}</text>')
