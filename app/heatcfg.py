"""Holdets farver og forklaringstekster for scorerne 1–5 (varmekort i tabeller, bane og diagrammer).

Gemmes som holdindstillinger: heat_color_<n> (#rrggbb), heat_label_<n> og heat_mode ('glide' = blandede overgange, 'blok' = én farve pr. hele tal).
Tom indstilling = standard. Indlæses én gang pr. forespørgsel (g.heat_cfg)."""
import re

DEFAULT_COLORS = ("#f8696b", "#ffeb84", "#63be7b", "#e0b020", "#9dc3e6")
DEFAULT_LABELS = ("Har brug for meget støtte", "Under årgangen", "På niveau med årgangen (målet)", "Over årgangen", "Meget stærk – bedre end årgangen")
MOTIVATION_LABELS = ("Slet ikke", "Lidt", "Nogenlunde", "Meget", "Rigtig meget")
MODES = {"glide": "Glidende (3,4 = blanding af 3 og 4)", "blok": "Faste blokke (afrundet)"}
HEX = re.compile(r"^#[0-9a-f]{6}$")
MAX_LABEL = 60


def default():
    return dict(colors=list(DEFAULT_COLORS), labels=list(DEFAULT_LABELS), mode="glide", custom=False)


def load(db, tid):
    from .db import get_setting
    cfg = default()
    for n in range(5):
        c = (get_setting(db, tid, f"heat_color_{n + 1}") or "").lower()
        if HEX.match(c):
            cfg["colors"][n], cfg["custom"] = c, True
        lab = (get_setting(db, tid, f"heat_label_{n + 1}") or "").strip()
        if lab:
            cfg["labels"][n], cfg["custom"] = lab[:MAX_LABEL], True
    m = get_setting(db, tid, "heat_mode")
    if m in MODES:
        cfg["mode"] = m
        cfg["custom"] = cfg["custom"] or m != "glide"
    return cfg


def save(db, tid, colors, labels, mode):
    """Gemmer kun afvigelser fra standarden. Returnerer fejltekst eller None."""
    from .db import set_setting
    for n, c in enumerate(colors):
        c = (c or "").lower()
        if not HEX.match(c):
            return f"Farven for {n + 1} skal være #RRGGBB."
    if mode not in MODES:
        return "Ukendt visning."
    for n in range(5):
        c = colors[n].lower()
        set_setting(db, tid, f"heat_color_{n + 1}", "" if c == DEFAULT_COLORS[n] else c)
        lab = (labels[n] or "").strip()[:MAX_LABEL]
        set_setting(db, tid, f"heat_label_{n + 1}", "" if lab == DEFAULT_LABELS[n] else lab)
    set_setting(db, tid, "heat_mode", "" if mode == "glide" else mode)
    return None


def reset(db, tid):
    from .db import set_setting
    for n in range(5):
        set_setting(db, tid, f"heat_color_{n + 1}", "")
        set_setting(db, tid, f"heat_label_{n + 1}", "")
    set_setting(db, tid, "heat_mode", "")


def current():
    """Det aktive holds farver (cachet pr. forespørgsel); uden for en forespørgsel eller uden hold: standard."""
    try:
        from flask import g, has_request_context
        if not has_request_context():
            return default()
        if "heat_cfg" not in g:
            if g.get("team"):
                from .db import get_db
                g.heat_cfg = load(get_db(), g.team["id"])
            else:
                g.heat_cfg = default()
        return g.heat_cfg
    except Exception:      # noqa: BLE001 – farver må aldrig vælte en side
        return default()


def mark_used():
    try:
        from flask import g, has_request_context
        if has_request_context():
            g.heat_used = True
    except Exception:      # noqa: BLE001
        pass


def rgb(hexcolor):
    return tuple(int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))


def text_color(hexcolor):
    """Sort eller hvid tekst, så tallet kan læses på baggrunden (relativ luminans)."""
    if not HEX.match(hexcolor or ""):
        return "#1b1b1b"
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g_, b = (lin(x) for x in rgb(hexcolor))
    return "#1b1b1b" if 0.2126 * r + 0.7152 * g_ + 0.0722 * b > 0.22 else "#ffffff"
