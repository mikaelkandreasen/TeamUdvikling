"""Jinja-filtre: danske tal/datoer, farver."""
from datetime import date

from . import charts, model


def dk(v, nd=1):
    if v is None or v == "":
        return ""
    try:
        return f"{float(v):.{nd}f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(v)


def pct(v):
    return "" if v is None else f"{round(v * 100)}%"


def signed(v, nd=1):
    if v is None:
        return ""
    s = f"{v:+.{nd}f}".replace(".", ",")
    return "±0" if float(v) == 0 else s


def date_dk(s):
    d = model.parse_date(s) if isinstance(s, str) else s
    return d.strftime("%d-%m-%Y") if isinstance(d, date) else ""


def heat(v):
    return charts.heat(v)


def delta_class(v):
    if v is None:
        return ""
    return "pos" if v > 0.05 else ("neg" if v < -0.05 else "")


def register(app):
    for f in (dk, pct, signed, date_dk, heat, delta_class):
        app.jinja_env.filters[f.__name__] = f
