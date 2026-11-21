"""Domænemodel: DBU's fire roller x seks nøglefærdigheder samt alle beregninger.

Filen indeholder INGEN spillerdata – kun definitioner og regneregler.
"""
import calendar
from datetime import date

ROLES = ["Boldholder", "Medspiller", "Presspiller", "Støttespiller"]
SKILLS = ["Teknik", "Bevægelse", "Scanning", "Timing", "Positionering", "Maskering"]
N_SKILLS = len(SKILLS)
N_CRIT = len(ROLES) * N_SKILLS  # 24
MAX_ROUNDS = 20
DEFAULT_ROUNDS = 4
ROUNDS = tuple(range(1, MAX_ROUNDS + 1))       # alle mulige runder; hvert hold bruger de første n (g.rounds)
# Positioner (dropdown). De seks gamle værdier er stadig gyldige, så eksisterende data virker uændret.
# «Kant» = kan spille begge sider; «Højre/Venstre kant» og back-positioner er set fra holdets egen retning (fremad).
POSITION_GROUPS = [
    ("Målmand", ["Målmand"]),
    ("Forsvar", ["Forsvar", "Højre back", "Venstre back", "Midtstopper"]),
    ("Midtbane", ["Midtbane", "Defensiv midtbane", "Offensiv midtbane"]),
    ("Kant", ["Kant", "Højre kant", "Venstre kant"]),
    ("Angreb", ["Angreb"]),
    ("Andet", ["Allround"]),
]
POSITIONS = [p for _g, items in POSITION_GROUPS for p in items]
MAX_POSITIONS = 4                                # op til 4 positionsvalg pr. spiller (rækkefølge = præference)
POSITION_FIELDS = ["position", "position2", "position3", "position4"]
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


# Spillerniveau: DBU's A, B, C, D (nybegynder) og Nystartet, plus A+ til den allerbedste del af A (egen gradering). Beskrivelserne er omskrevet med egne ord; se LEVEL_SOURCE
LEVELS = ("A+", "A", "B", "C", "D", "Nystartet")
LEVEL_LABEL = {"D": "D (nybegynder)"}
LEVEL_ORD = {"Nystartet": 1, "D": 2, "C": 3, "B": 4, "A": 5, "A+": 6}          # bruges til at beregne et gennemsnit af trænernes vurderinger
LEVEL_SOURCE = "https://www.dbufyn.dk/boern-u5-12/generelt-om-boernefodbold/niveaudeling-til-staevner/#Niveauer"
LEVEL_INFO = (
    ("A+", "A+ (de allerstærkeste)", "Ikke et DBU-niveau, men en gradering i appen: spillere i toppen af A-niveauet, som tydeligt er blandt de stærkeste på holdet."),
    ("A", "A-niveau", "Børn der elsker fodbold og spiller meget, både hjemme og i skolen. De løber hurtigt, sparker godt og har styr på bolden i fart. "
          "De forstår som regel spillet, læser situationerne og er i gang, før tingene sker. Et A-hold består af A- og B-spillere – ikke C-spillere. "
          "Niveauet er for helt almindelige børn, ikke for talentakademier."),
    ("B", "B-niveau", "Spillere der ligger mellem A og C. Et B-hold består mest af B-spillere, gerne med et par C-spillere og højst én A-spiller."),
    ("C", "C-niveau", "Børn der er nye i fodbold eller endnu ikke har fanget, hvad spillet går ud på. De har ofte ikke spillet længe og skal bruge længere tid på at styre bolden – "
          "typisk sent fødte, forsigtige eller nystartede børn. Et C-hold består udelukkende af C-spillere; kommer der en A-spiller eller to-tre B-spillere på, er det ikke længere et C-hold."),
    ("D", "D-niveau (nybegynder)", "DBU kalder dem begyndere: de mindst erfarne C-spillere og D-spillere. Børn der stadig er i gang med at lære bolden og spillet at kende."),
    ("Nystartet", "Nystartet", "Børn der er helt nye i både bevægelse og fodbold, ofte taget med af forældrene eller på prøve for at se, om det er noget for dem. "
          "De sparker tit forbi bolden, er bange for den, når den kommer flyvende, og lader sig let aflede. Et nystartet-hold har ingen A- eller B-spillere og højst et par C-spillere. "
          "Når holdet fører med 3 mål, tages en spiller af banen, og ved 6 mål endnu en."),
)
LEVEL_TEAMS = (
    "A-hold: består primært af A- og B-spillere; C-spillere må gerne være med, de udvikler sig også af det. Har årgangen 3-4 A-spillere, eller en-to spillere der kan afgøre kampe, hører holdet hjemme i A-rækken.",
    "B-hold: 0-2 A-spillere og primært B-spillere. Tre eller flere A-spillere er ikke i orden i et B-stævne. C-spillere er velkomne.",
    "C-hold: ingen A-spillere og højst 1-2 B-spillere. Rent begynderhold: sent fødte, nystartede, forsigtige børn, der har brug for tid og plads til at lykkes.",
    "D- og nybegynderhold: ingen A- og B-spillere og højst 1-2 C-spillere. Ingen for gamle spillere eller dispensationsspillere.",
    "Fleksibilitet: niveauet er ikke mejslet i granit. Efter et stævne uden nederlag bør holdet rykke en række op; uden en eneste sejr kan man overveje en lavere række; "
    "ved fx tre nederlag, hvoraf to var tætte, bør man kraftigt overveje at blive i rækken.")
LEVEL_NOTES = ("Blandet niveau: alle spiller med og mod hinanden uanset niveau, og klubben bør blande sine spillere på tværs af hold i stedet for et rent A-hold mod et rent C-hold.",
               "Børn udvikler sig forskelligt og skifter niveau over tid. Placér spillerne efter deres faktiske niveau, og flyt ikke A- og B-spillere ned på C-hold.")
# Hvorfor har spilleren fået mascotten med hjem?
MASCOT_REASONS = {"indsats": "Flot indsats", "fremgang": "Stor fremgang", "kammerat": "God kammerat", "hjaelp": "Hjælpsom",
                  "foerste": "Første gang / tur", "fodselsdag": "Fødselsdag", "andet": "Andet"}


# ---------------------------------------------------------------- niveauvurdering efter DBU's udsagn (A/B/C/D-kolonner)
# Ti kompetencer/præferencer × udsagn pr. niveau (omskrevet med egne ord ud fra DBU Fyns regneark «Niveaudeling»; kilde: LEVEL_SOURCE).
DBU_COLS = ("A", "B", "C", "D")
DBU_ITEMS = (
    ("engagement", "Engagement", {
        "A": "Møder op hver gang, spiller konstant hjemme og i skolen og har spillet i nogen tid.",
        "B": "Møder op hver gang, spiller meget hjemme og i skolen og har spillet i nogen tid.",
        "C": "Møder op stort set hver gang og spiller lidt hjemme og i skolen.",
        "D": "Spørger hurtigt om ting, der ikke handler om fodbold (fx hvad man spiste i går) – fodbold er ikke første prioritet i deres liv."}),
    ("interesse", "Interesse", {
        "A": "Synes fodbold er det bedste i verden.",
        "B": "Synes fodbold er det bedste i verden.",
        "C": "Synes fodbold er fint, men ikke det vigtigste – kommer især, fordi kammeraterne kommer.",
        "D": "Kan være lokket afsted af forældre eller klub, eller vil lige snuse til det for at se, om det er noget for dem."}),
    ("viden", "Viden", {
        "A": "Har i store træk knækket koden til, hvad fodbold går ud på.",
        "B": "Har i store træk knækket koden til, hvad fodbold går ud på.",
        "C": "Er lige startet eller har endnu ikke knækket koden til spillet.",
        "D": "Ved, hvad fodbold går ud på, fordi de har set andre spille det."}),
    ("forstaaelse", "Forståelse", {
        "A": "Kigger efter spillet, forsøger at forudsige, hvor bolden kommer hen, og er i løb, før tingene sker.",
        "B": "Kigger indimellem væk fra bolden og løber ofte, før tingene sker.",
        "C": "Kigger mest på bolden og løber ofte først, når tingene sker.",
        "D": "Kigger mest på bolden og løber ofte først, når tingene sker eller er sket – kigger efter flyvemaskiner eller leder efter firkløvere."}),
    ("teknik", "Teknik", {
        "A": "Kontrollerer nemt bolden uden pres.",
        "B": "Kontrollerer for det meste bolden uden pres.",
        "C": "Kræver mere tid til at kontrollere bolden.",
        "D": "Er udfordret af at kontrollere bolden, hvis den kommer for hårdt eller hurtigt – også når de ikke er presset."}),
    ("boldkontrol", "Boldkontrol", {
        "A": "Kan kontrollere bolden i løb.",
        "B": "Kan drible i løb.",
        "C": "Kan drible, men mister bolden i for høj fart.",
        "D": "Mister bolden, hvis der løbes hurtigt med den."}),
    ("spark", "Spark", {
        "A": "Sparker godt.",
        "B": "Sparker fint.",
        "C": "Behøver ikke at kunne sparke langt eller præcist.",
        "D": "Sparker flere huller i græsset eller i luften, end de rammer bolden – sparker skævt."}),
    ("hurtighed", "Hurtighed", {
        "A": "Løber hurtigt.",
        "B": "Har rimelig kondition.",
        "C": "Bliver hurtigt træt eller er langsom.",
        "D": "(Ingen D-tekst i DBU's ark) Vælg D, hvis spilleren er endnu langsommere eller mere udkørt end C-beskrivelsen."}),
    ("motorik", "Motorik", {
        "A": "Fin motorik – kan vende kroppen og løbe modsat i god fart.",
        "B": "Okay motorik – kan vende kroppen og løbe modsat i rimelig fart.",
        "C": "Kan være motorisk udfordret.",
        "D": "Nybegynder i generel bevægelse og motorik."}),
    ("fysik", "Fysik", {
        "A": "Relativt stor for alderen og bruger kroppen i dueller.",
        "B": "Gennemsnitlig størrelse for alderen.",
        "C": "Lille eller bruger ikke kroppen godt i dueller.",
        "D": "Kan være bange for at slå sig."}),
)
DBU_KEYS = frozenset(f"{k}.{c}" for k, _, txt in DBU_ITEMS for c in txt)
DBU_WEIGHT = {"A": 4, "B": 3, "C": 2, "D": 1}      # kun til at rangere spillere med samme niveau


def dbu_result(ticked):
    """ticked: mængde af 'kompetence.kolonne' – ét valg (A/B/C/D) pr. kompetence. Returnerer None uden valg, ellers dict(level, a, b, c, d, n, points).
    Regel: bliver alle ti kompetencer scoret A, er spilleren A+. Ellers er niveauet det, der er flest af; ved lighed vælges det højeste (DBU: start altid ved A)."""
    pick = {}
    for x in ticked:
        if x in DBU_KEYS:
            k, c = x.split(".")
            pick[k] = c
    if not pick:
        return None
    n = {c: sum(1 for v in pick.values() if v == c) for c in DBU_COLS}
    if n["A"] == len(DBU_ITEMS):
        lv = "A+"
    else:
        top = max(n.values())
        lv = next(c for c in DBU_COLS if n[c] == top)                 # A, B, C, D i rækkefølge → ved lighed det højeste
    return dict(level=lv, a=n["A"], b=n["B"], c=n["C"], d=n["D"], n=len(pick), points=sum(DBU_WEIGHT[c] * n[c] for c in DBU_COLS))


# ---------------------------------------------------------------- beregnet niveau (som standard 25 % A / 50 % B / 25 % C)
DEFAULT_SHARES = (25, 25)          # procent A og procent C (B er resten) – kan justeres pr. hold under holdindstillinger


def distribute_levels(scores, a_pct=25, c_pct=25):
    """{spiller: score} -> {spiller: 'A'|'B'|'C'}. De øverste a_pct % er A, de nederste c_pct % C, resten B (ud fra score).
    Ved lighed på grænsen følger spilleren den bedre gruppe; er alle ens, er alle B."""
    vals = {k: v for k, v in scores.items() if v is not None}
    if not vals:
        return {}
    n = len(vals)
    order = sorted(vals.values(), reverse=True)
    if order[0] == order[-1]:
        return {k: "B" for k in vals}
    ka = int(n * a_pct / 100 + 0.5)
    kc = int(n * c_pct / 100 + 0.5)
    a_cut = order[ka - 1] if ka else None
    c_cut = order[n - kc] if kc else None
    out = {}
    for pid, v in vals.items():
        if a_cut is not None and v >= a_cut:
            out[pid] = "A"
        elif c_cut is not None and v <= c_cut:
            out[pid] = "C"
        else:
            out[pid] = "B"
    return out
