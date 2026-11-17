"""Domænemodel: DBU's fire roller x seks nøglefærdigheder samt alle beregninger.

Filen indeholder INGEN spillerdata – kun definitioner og regneregler.
"""
import calendar
from datetime import date

ROLES = ["Boldholder", "Medspiller", "Presspiller", "Støttespiller"]
SKILLS = ["Teknik", "Bevægelse", "Scanning", "Timing", "Positionering", "Maskering"]
N_SKILLS = len(SKILLS)
N_CRIT = len(ROLES) * N_SKILLS  # 24
ROUNDS = (1, 2, 3, 4)
POSITIONS = ["Målmand", "Forsvar", "Midtbane", "Kant", "Angreb", "Allround"]
FEET = ["Højre", "Venstre", "Begge"]
STATUSES = ["Ikke startet", "I gang", "Nået", "Udskudt"]
SCALE = "1 = Slet ikke | 2 = Lidt | 3 = Nogenlunde | 4 = Meget | 5 = Rigtig meget"
EVAL_SCALE = "1 = Har brug for meget støtte | 3 = På niveau med årgangen | 5 = Meget stærk"

ROLE_DEF = {
    "Boldholder": "Spilleren med bolden. Vælger, om der skal afleveres, driblet eller afsluttes.",
    "Medspiller": "Hjælper boldholder ved at løbe sig fri og blive spilbar i gode positioner.",
    "Presspiller": "Typisk den spiller, der er nærmest boldholder, og som kan presse og vinde bolden.",
    "Støttespiller": "Vurderer hele tiden, om bolden kan erobres, og sikrer defensiv balance ved at dække op bag presspilleren.",
}
DESC = {
    "Boldholder": [
        "Førstebetjening, boldkontrol, aflevering, dribling og afslutning – også med en modstander tæt på.",
        "Bevæger sig med bolden: temposkift, retningsskift og vendinger, der skaber tid og plads.",
        "Kigger op før og efter modtagelse og ser medspillere, modstandere og rum, før næste valg tages.",
        "Vælger tidspunkt til at aflevere, drible eller afslutte – hverken for tidligt eller for sent.",
        "Placerer sig og bolden, så der er afleveringsmuligheder, og beskytter bolden mod presset.",
        "Skjuler sin hensigt med krop, blik og finter, så modstanderen ikke kan læse næste aktion.",
    ],
    "Medspiller": [
        "Modtager og spiller videre i bevægelse med få berøringer og god førstebetjening.",
        "Løber sig fri (ud af skyggen, modløb, dybdeløb) og er spilbar for boldholder.",
        "Orienterer sig om bold, modstandere og rum, før bolden kommer, og vælger løb derefter.",
        "Viser sig og løber på det rigtige tidspunkt – når boldholder kan se og spille bolden.",
        "Finder gode positioner i bredde og dybde, skaber vinkler og bruger rummene mellem modstanderne.",
        "Lokker modstanderen væk med forfinteløb og blikretning, så rum eller aflevering åbnes.",
    ],
    "Presspiller": [
        "Tackling, blokering og erobring af bolden i 1-mod-1 uden at gå i jorden for tidligt.",
        "Hurtig tilnærmelse til boldholder, derefter kontrollerede små skridt og hurtig reaktion på retningsskift.",
        "Aflæser boldholder, medspillere og eget holds placering, før og under presset.",
        "Vælger det rette tidspunkt til at presse og gå i tacklingen – fx ved dårlig førstebetjening.",
        "Placerer sig mellem bold og mål, holder passende afstand og styrer boldholder mod en side.",
        "Skjuler pres-hensigten og lukker afleveringsveje, så boldholder lokkes mod en side eller en fejl.",
    ],
    "Støttespiller": [
        "Opsnapper, blokerer og tackler løse bolde og har ro på bolden efter en erobring.",
        "Hurtig omstilling og kovending; kan rykke ind og overtage presrollen, hvis presspiller overspilles.",
        "Overblik over bold, presspiller og de modstandere, der kan modtage; vurderer hele tiden, om bolden kan erobres.",
        "Rykker ind, overtager pres eller opsnapper en aflevering på det rette tidspunkt.",
        "Dækker op bag presspilleren og sikrer defensiv balance med passende afstand til bold og modstander.",
        "Skjuler, at man er klar til at opsnappe, og lukker ind i sidste øjeblik.",
    ],
}
CRITERIA = [
    dict(idx=r * N_SKILLS + s, r=r, s=s, role=ROLES[r], skill=SKILLS[s], desc=DESC[ROLES[r]][s])
    for r in range(len(ROLES)) for s in range(N_SKILLS)
]

TRIVSEL = ["Jeg har det godt til træning", "Jeg føler mig som en del af holdet", "Jeg tør prøve nye ting og begå fejl"]
MOTORIK = ["Balance", "Koordination", "Hurtige fødder / agility", "Spændstighed (hop)"]

# Motivationsskema: 3 kategorier med 8 + 8 + 6 pladser. Tomme tekster = ledige pladser.
CAT_SIZES = (8, 8, 6)
DEFAULT_CATEGORIES = [
    ("Hvorfor går jeg til fodbold?", [
        "Jeg går til fodbold, fordi det er sjovt.",
        "Jeg går til fodbold for at være sammen med mine venner og holdkammerater.",
        "Jeg vil gerne blive dygtigere til fodbold.",
        "Jeg synes, det er spændende at spille kampe."]),
    ("Mine ønsker til træningen", [
        "Jeg vil gerne have mere spil (små kampe) til træning.",
        "Jeg vil gerne have flere øvelser, hvor jeg lærer nye tricks og færdigheder.",
        "Jeg vil gerne have flere tips og mere feedback fra trænerne.",
        "Jeg vil gerne være med til at bestemme, hvad vi laver til træning."]),
    ("Ekstra kategori (skriv titel her)", []),
]


def cat_of(qidx):
    start = 0
    for cat, n in enumerate(CAT_SIZES):
        if qidx < start + n:
            return cat
        start += n
    raise ValueError(qidx)


N_Q = sum(CAT_SIZES)  # 22

# ---------------------------------------------------------------- beregninger


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def interpret(enighed):
    if enighed is None:
        return ""
    if enighed <= 1:
        return "Høj enighed"
    if enighed <= 2:
        return "Moderat forskel"
    return "Stor forskel – drøft observationer"


def compute_round(rows):
    """rows: iterable af (player_id, trainer_id, crit, score) for én runde.

    Samlet = gennemsnit af de fire rolle-gennemsnit. Rolle-gennemsnit pr. spiller = gennemsnit over
    trænernes egne rolle-gennemsnit. Enighed = størst minus mindst samlet score mellem trænere (mindst 2).
    """
    data = {}
    for pid, tid, crit, score in rows:
        data.setdefault(pid, {}).setdefault(tid, {})[crit] = score
    out = {}
    for pid, trainers in data.items():
        t_roles, t_samlet = {}, {}
        for tid, sc in trainers.items():
            ra = [mean([sc.get(r * N_SKILLS + s) for s in range(N_SKILLS)]) for r in range(len(ROLES))]
            t_roles[tid] = ra
            t_samlet[tid] = mean(ra)
        roles = [mean([ra[r] for ra in t_roles.values()]) for r in range(len(ROLES))]
        crit = [mean([sc.get(i) for sc in trainers.values()]) for i in range(N_CRIT)]
        vals = [v for v in t_samlet.values() if v is not None]
        enighed = (max(vals) - min(vals)) if len(vals) >= 2 else None
        out[pid] = dict(roles=roles, crit=crit, samlet=mean(roles), enighed=enighed,
                        fortolkning=interpret(enighed), trainers=len(trainers), trainer_samlet=t_samlet)
    return out


def load_rounds(db, team_id):
    """Returnerer {runde: {player_id: resultat}} for alle fire runder – kun for ét hold."""
    grouped = {r: [] for r in ROUNDS}
    for row in db.execute("SELECT e.round, e.player_id, e.trainer_id, e.crit, e.score FROM evaluations e "
                          "JOIN players p ON p.id=e.player_id WHERE p.team_id=?", (team_id,)):
        if row["round"] in grouped:
            grouped[row["round"]].append((row["player_id"], row["trainer_id"], row["crit"], row["score"]))
    return {r: compute_round(rows) for r, rows in grouped.items()}


def skill_avgs(crit):
    """Gennemsnit pr. nøglefærdighed (over de fire roller) ud fra liste med 24 kriterie-gennemsnit."""
    return [mean([crit[r * N_SKILLS + s] for r in range(len(ROLES))]) for s in range(N_SKILLS)]


def latest(rounds, pid):
    """(runde, resultat) for spillerens nyeste runde med samlet score – ellers (None, None)."""
    for r in reversed(ROUNDS):
        res = rounds.get(r, {}).get(pid)
        if res and res["samlet"] is not None:
            return r, res
    return None, None


def area_development(rounds, player_ids):
    """Holdets gennemsnit pr. rolle og pr. nøglefærdighed for hver runde (kun de angivne spillere)."""
    roles = {r: [] for r in ROUNDS}
    skills = {r: [] for r in ROUNDS}
    samlet = {}
    for r in ROUNDS:
        res = [rounds[r][p] for p in player_ids if p in rounds[r]]
        roles[r] = [mean([x["roles"][i] for x in res]) for i in range(len(ROLES))]
        skills[r] = [mean([skill_avgs(x["crit"])[s] for x in res]) for s in range(N_SKILLS)]
        samlet[r] = mean([x["samlet"] for x in res])
    return roles, skills, samlet


# ---------------------------------------------------------------- relativ alder


def parse_date(s):
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def quarter(d):
    return (d.month - 1) // 3 + 1


def months_after_jan1(d):
    dim = calendar.monthrange(d.year, d.month)[1]
    return round(d.month - 1 + (d.day - 1) / dim, 1)


def age_note(q):
    return {
        1: "Født i 1. kvartal – relativt ældst i årgangen. Kan have fysisk forspring; vurder færdigheder med det in mente.",
        2: "Født i 2. kvartal – lidt ældre end gennemsnittet i årgangen.",
        3: "Født i 3. kvartal – lidt yngre end gennemsnittet i årgangen.",
        4: "Født i 4. kvartal – relativt yngst i årgangen. Kan være fysisk bagud; giv tid og spilletid, og vurder potentiale – ikke kun niveau.",
    }.get(q, "")


def ratio(num, den):
    if num is None or not den:
        return None
    return num / den
