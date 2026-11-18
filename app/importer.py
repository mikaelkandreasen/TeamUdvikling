"""Import af hold- og spillerdata fra CSV/XLSX (kun administrator).

To trin: 1) upload → validering og forhåndsvisning (intet gemmes i databasen), 2) bekræft → gem.
Mellemresultatet ligger kort som fil i /data/import (knyttet til administratoren, slettes ved bekræftelse eller efter 30 min).
Formler i Excel køres aldrig (kun gemte værdier læses). Revisionsloggen får kun antal – aldrig navne.
"""
import csv
import io
import json
import os
import re
import secrets
import time
import zipfile
from datetime import date, datetime

from . import model

MAX_ROWS = 2000
MAX_UNZIPPED = 20 * 1024 * 1024
TTL = 30 * 60
COLUMNS = ["Hold", "Sæson", "Navn", "Fødselsdato", "Trøjenr", "Position", "Sekundær position", "Fod", "Startdato", "Fokus 1", "Fokus 2", "Noter", "Aktiv"]
ALIASES = {
    "team": "hold", "holdnavn": "hold", "saeson": "sæson", "season": "sæson",
    "name": "navn", "spiller": "navn", "spillernavn": "navn",
    "fodselsdato": "fødselsdato", "foedselsdato": "fødselsdato", "født": "fødselsdato", "foedt": "fødselsdato", "birth_date": "fødselsdato", "birthdate": "fødselsdato",
    "trojenr": "trøjenr", "trøje": "trøjenr", "trøjenummer": "trøjenr", "nr": "trøjenr", "shirt": "trøjenr", "shirt_no": "trøjenr",
    "sekundær": "sekundær position", "sekundaer": "sekundær position", "position2": "sekundær position", "sekundær position": "sekundær position",
    "foot": "fod", "start": "startdato", "start_date": "startdato", "fokus1": "fokus 1", "fokus2": "fokus 2",
    "notes": "noter", "note": "noter", "active": "aktiv",
}
KEYS = {"hold": "team", "sæson": "season", "navn": "name", "fødselsdato": "birth_date", "trøjenr": "shirt_no", "position": "position",
        "sekundær position": "position2", "fod": "foot", "startdato": "start_date", "fokus 1": "focus1", "fokus 2": "focus2", "noter": "notes", "aktiv": "active"}
LIMITS = {"team": 80, "season": 20, "name": 80, "shirt_no": 10, "focus1": 200, "focus2": 200, "notes": 1000}


class ImportError_(ValueError):
    """Fejl i selve filen (ikke i en enkelt række)."""


def _norm_header(h):
    h = str(h or "").strip().lower()
    h = re.sub(r"\s+", " ", h)
    return ALIASES.get(h, ALIASES.get(h.replace(" ", ""), h))


def _read_table(data, filename):
    """Returnerer liste af rækker (lister af tekst/dato/None). Første række er overskrifter."""
    if data[:2] == b"PK":                                   # xlsx er en zip
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
                    raise ImportError_("Excel-filen er for stor.")
        except zipfile.BadZipFile:
            raise ImportError_("Filen kunne ikke læses som Excel.")
        from openpyxl import load_workbook
        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)   # data_only: formler køres aldrig
        except Exception:
            raise ImportError_("Filen kunne ikke læses som Excel.")
        ws = wb.worksheets[0]
        rows = []
        for r in ws.iter_rows(values_only=True):
            rows.append(list(r))
            if len(rows) > MAX_ROWS + 1:
                break
        wb.close()
        return rows
    if not (filename or "").lower().endswith((".csv", ".txt")):
        raise ImportError_("Upload en .xlsx- eller .csv-fil.")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ImportError_("Tegnsættet kunne ikke genkendes (brug UTF-8).")
    head = text[:2000]
    delim = max((";", ",", "\t"), key=head.count)
    return [r for r in csv.reader(io.StringIO(text), delimiter=delim)][: MAX_ROWS + 2]


def _date(v):
    if v is None or v == "":
        return "", None
    if isinstance(v, datetime):
        v = v.date()
    if isinstance(v, date):
        return v.isoformat(), None
    s = str(v).strip()
    for pat in (r"^(\d{4})-(\d{1,2})-(\d{1,2})$", r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$"):
        m = re.match(pat, s)
        if m:
            a, b, c = (int(x) for x in m.groups())
            y, mo, d = (a, b, c) if pat.startswith("^(\\d{4})") else (c, b, a)
            try:
                return date(y, mo, d).isoformat(), None
            except ValueError:
                break
    return "", f"ugyldig dato '{s[:20]}' (brug ÅÅÅÅ-MM-DD eller DD-MM-ÅÅÅÅ)"


def _text(v, key):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()[: LIMITS.get(key, 100)]


def parse(data, filename, default_team):
    """Validerer en fil. Returnerer dict(rows=[...], teams=[...]). Hver række: status ny/opdater/fejl, warnings, værdier."""
    table = _read_table(data, filename)
    if not table:
        raise ImportError_("Filen er tom.")
    header = [_norm_header(h) for h in table[0]]
    if "navn" not in header:
        raise ImportError_("Kolonnen 'Navn' mangler. Hent skabelonen for at se de forventede kolonner.")
    if "hold" not in header and not default_team:
        raise ImportError_("Filen har ingen kolonne 'Hold', og der er intet aktivt hold.")
    idx = {KEYS[h]: i for i, h in enumerate(header) if h in KEYS}
    body = [r for r in table[1:] if any(str(c or "").strip() for c in r)]
    if len(body) > MAX_ROWS:
        raise ImportError_(f"Filen har mere end {MAX_ROWS} rækker. Del den op.")
    rows, seen = [], set()
    for n, r in enumerate(body, start=2):
        get = lambda k: r[idx[k]] if k in idx and idx[k] < len(r) else None
        v, warn, err = {}, [], None
        for k in ("team", "season", "name", "shirt_no", "focus1", "focus2", "notes"):
            v[k] = _text(get(k), k)
        if "team" not in idx:
            v["team"] = default_team
        for k in ("birth_date", "start_date"):
            v[k], w = _date(get(k))
            if w:
                warn.append(f"{k.replace('_', ' ')}: {w}")
        for k, choices in (("position", model.POSITIONS), ("position2", model.POSITIONS), ("foot", model.FEET)):
            raw = _text(get(k), k)
            match = next((c for c in choices if c.lower() == raw.lower()), "") if raw else ""
            if raw and not match:
                warn.append(f"{k}: ukendt værdi '{raw[:20]}' (ignoreret)")
            v[k] = match
        act = _text(get("active"), "active").lower()
        v["active"] = 0 if act in ("nej", "n", "0", "false", "inaktiv") else 1
        if not v["name"]:
            err = "navn mangler"
        elif not v["team"]:
            err = "hold mangler"
        key = (v["team"].lower(), v["name"].lower(), v["birth_date"])
        if not err and key in seen:
            err = "dublet i filen"
        seen.add(key)
        rows.append(dict(line=n, error=err, warnings=warn, **v))
    return dict(rows=rows, teams=sorted({r["team"] for r in rows if not r["error"]}))


def classify(db, parsed):
    """Tilføjer status: ny / opdater / fejl, og markerer nye hold."""
    existing_teams = {r["name"].lower(): r["id"] for r in db.execute("SELECT id,name FROM teams")}
    for r in parsed["rows"]:
        if r["error"]:
            r["status"] = "fejl"
            continue
        tid = existing_teams.get(r["team"].lower())
        r["new_team"] = tid is None
        r["status"] = "ny"
        if tid:
            hit = db.execute("SELECT id FROM players WHERE team_id=? AND lower(name)=? AND coalesce(birth_date,'')=?",
                             (tid, r["name"].lower(), r["birth_date"])).fetchone()
            if hit:
                r["status"], r["player_id"] = "opdater", hit["id"]
    parsed["new_teams"] = sorted({r["team"] for r in parsed["rows"] if r.get("new_team")})
    parsed["counts"] = {s: sum(1 for r in parsed["rows"] if r["status"] == s) for s in ("ny", "opdater", "fejl")}
    return parsed


def apply(db, parsed):
    """Gemmer gyldige rækker. Returnerer (nye, opdaterede, nye_hold). Kald db.commit() udenfor."""
    from .db import create_team
    teams = {r["name"].lower(): r["id"] for r in db.execute("SELECT id,name FROM teams")}
    seasons = {}
    for r in parsed["rows"]:
        if r["season"] and not r["error"]:
            seasons.setdefault(r["team"].lower(), r["season"])
    new_n = upd_n = team_n = 0
    for r in parsed["rows"]:
        if r["error"]:
            continue
        k = r["team"].lower()
        if k not in teams:
            teams[k] = create_team(db, r["team"], seasons.get(k, ""))
            team_n += 1
        tid = teams[k]
        hit = db.execute("SELECT id FROM players WHERE team_id=? AND lower(name)=? AND coalesce(birth_date,'')=?",
                         (tid, r["name"].lower(), r["birth_date"])).fetchone()
        cols = ["shirt_no", "position", "position2", "foot", "start_date", "focus1", "focus2", "notes"]
        if hit:                                                 # opdatér kun felter, der er udfyldt i filen
            sets = [c for c in cols if r[c]]
            db.execute(f"UPDATE players SET {','.join(c + '=?' for c in sets + ['active'])} WHERE id=?",
                       [r[c] for c in sets] + [r["active"], hit["id"]])
            upd_n += 1
        else:
            db.execute("INSERT INTO players(team_id,name,birth_date,shirt_no,position,position2,foot,start_date,focus1,focus2,notes,active)"
                       " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                       [tid, r["name"], r["birth_date"] or None] + [r[c] or None for c in cols] + [r["active"]])
            new_n += 1
    return new_n, upd_n, team_n


# ---------------------------------------------------------------- mellemlager (engangsfil pr. upload)
def _dir(data_dir):
    d = os.path.join(data_dir, "import")
    os.makedirs(d, exist_ok=True)
    return d


def stash(data_dir, user_id, parsed):
    d = _dir(data_dir)
    for f in os.listdir(d):                                    # ryd op
        p = os.path.join(d, f)
        if time.time() - os.path.getmtime(p) > TTL:
            os.remove(p)
    token = secrets.token_urlsafe(18)
    path = os.path.join(d, token + ".json")
    with open(path, "w", encoding="utf8") as f:
        json.dump(dict(user_id=user_id, ts=time.time(), parsed=parsed), f, ensure_ascii=False)
    os.chmod(path, 0o600)
    return token


def unstash(data_dir, user_id, token):
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,40}", token or ""):
        return None
    path = os.path.join(_dir(data_dir), token + ".json")
    try:
        with open(path, encoding="utf8") as f:
            obj = json.load(f)
        os.remove(path)
    except (OSError, ValueError):
        return None
    if obj["user_id"] != user_id or time.time() - obj["ts"] > TTL:
        return None
    return obj["parsed"]


def template_csv():
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(COLUMNS)
    w.writerow(["U11 piger", "2026/27", "Anna Alfa", "2016-03-10", "7", "Midtbane", "Angreb", "Højre", "2026-08-01", "Scanning", "Timing", "", "ja"])
    return ("﻿" + out.getvalue()).encode("utf8")


def template_xlsx():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Spillere"
    ws.append(COLUMNS)
    ws.append(["U11 piger", "2026/27", "Anna Alfa", "2016-03-10", "7", "Midtbane", "Angreb", "Højre", "2026-08-01", "Scanning", "Timing", "", "ja"])
    info = wb.create_sheet("Vejledning")
    for line in ("Kolonnen Navn er påkrævet. Hold er valgfri (uden Hold bruges det aktive hold; nye hold oprettes).",
                 "Datoer: ÅÅÅÅ-MM-DD eller DD-MM-ÅÅÅÅ.", "Position: " + ", ".join(model.POSITIONS), "Fod: " + ", ".join(model.FEET),
                 "Aktiv: ja/nej (standard ja). Findes spilleren allerede (samme hold, navn og fødselsdato), opdateres udfyldte felter.",
                 "Slet eksempelrækken før upload."):
        info.append([line])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
