"""Sprog: dansk er kildesproget (selve teksten er nøglen); engelsk, tysk, svensk og norsk slås op i tabellen TR.

`_("Tekst")` i skabeloner returnerer oversættelsen for det aktive sprog, ellers den danske tekst (manglende oversættelser er altså aldrig tomme).
Sprog vælges med cookie `lang` (også på login-siden) og gemmes på brugeren (users.lang). Fejlbeskeder og indhold i Python-koden er endnu på dansk.
"""
from flask import g, request

LANGS = {"da": "Dansk", "en": "English", "de": "Deutsch", "sv": "Svenska", "no": "Norsk"}
DEFAULT = "da"
COOKIE = "lang"

# dansk: (en, de, sv, no)
_T = {
    "Hjem": ("Home", "Start", "Hem", "Hjem"),
    "Spillere": ("Players", "Spielerinnen", "Spelare", "Spillere"),
    "Evaluering": ("Evaluation", "Bewertung", "Utvärdering", "Evaluering"),
    "Evaluér": ("Evaluate", "Bewerten", "Utvärdera", "Evaluer"),
    "Teamoversigt": ("Team overview", "Teamübersicht", "Lagöversikt", "Lagoversikt"),
    "Udvikling": ("Development", "Entwicklung", "Utveckling", "Utvikling"),
    "Position & bane": ("Position & pitch", "Position & Spielfeld", "Position & plan", "Posisjon & bane"),
    "Holdsætning": ("Line-up", "Aufstellung", "Laguppställning", "Lagoppstilling"),
    "Kampe": ("Matches", "Spiele", "Matcher", "Kamper"),
    "Kampe og spilletid": ("Matches and playing time", "Spiele und Spielzeit", "Matcher och speltid", "Kamper og spilletid"),
    "Områder": ("Focus areas", "Bereiche", "Områden", "Områder"),
    "Motivation": ("Motivation", "Motivation", "Motivation", "Motivasjon"),
    "Udviklingsdata": ("Development data", "Entwicklungsdaten", "Utvecklingsdata", "Utviklingsdata"),
    "Fremmøde": ("Attendance", "Anwesenheit", "Närvaro", "Oppmøte"),
    "Rapporter": ("Reports", "Berichte", "Rapporter", "Rapporter"),
    "Rapport": ("Report", "Bericht", "Rapport", "Rapport"),
    "Skala & kriterier": ("Scale & criteria", "Skala & Kriterien", "Skala & kriterier", "Skala & kriterier"),
    "Beskeder": ("Messages", "Nachrichten", "Meddelanden", "Meldinger"),
    "Nye beskeder": ("New messages", "Neue Nachrichten", "Nya meddelanden", "Nye meldinger"),
    "flere i indbakken.": ("more in the inbox.", "weitere im Posteingang.", "fler i inkorgen.", "flere i innboksen."),
    "Læst": ("Read", "Gelesen", "Läst", "Lest"),
    "Min konto": ("My account", "Mein Konto", "Mitt konto", "Min konto"),
    "Administration": ("Administration", "Verwaltung", "Administration", "Administrasjon"),
    "Mere": ("More", "Mehr", "Mer", "Mer"),
    "Menu": ("Menu", "Menü", "Meny", "Meny"),
    "Hovedmenu": ("Main menu", "Hauptmenü", "Huvudmeny", "Hovedmeny"),
    "Hovedmenu (mobil)": ("Main menu (mobile)", "Hauptmenü (mobil)", "Huvudmeny (mobil)", "Hovedmeny (mobil)"),
    "Skift profil": ("Switch profile", "Profil wechseln", "Byt profil", "Bytt profil"),
    "Skift hold": ("Switch team", "Team wechseln", "Byt lag", "Bytt lag"),
    "Skift": ("Switch", "Wechseln", "Byt", "Bytt"),
    "(arkiveret)": ("(archived)", "(archiviert)", "(arkiverat)", "(arkivert)"),
    "Log ud": ("Log out", "Abmelden", "Logga ut", "Logg ut"),
    "Du ser siden som": ("You are viewing the page as", "Du siehst die Seite als", "Du ser sidan som", "Du ser siden som"),
    "(skrivebeskyttet)": ("(read-only)", "(schreibgeschützt)", "(skrivskyddad)", "(skrivebeskyttet)"),
    "Afslut": ("Stop", "Beenden", "Avsluta", "Avslutt"),
    "Privatliv": ("Privacy", "Datenschutz", "Integritet", "Personvern"),
    "Sprog": ("Language", "Sprache", "Språk", "Språk"),
    "Log ind": ("Log in", "Anmelden", "Logga in", "Logg inn"),
    "Brugernavn": ("Username", "Benutzername", "Användarnamn", "Brukernavn"),
    "Adgangskode": ("Password", "Passwort", "Lösenord", "Passord"),
    "Fortsæt": ("Continue", "Weiter", "Fortsätt", "Fortsett"),
    "Efter adgangskoden skal du angive en engangskode fra din autentificeringsapp (2FA).": (
        "After the password you enter a one-time code from your authenticator app (2FA).",
        "Nach dem Passwort gibst du einen Einmalcode aus deiner Authentifizierungs-App ein (2FA).",
        "Efter lösenordet anger du en engångskod från din autentiseringsapp (2FA).",
        "Etter passordet oppgir du en engangskode fra autentiseringsappen din (2FA)."),
    "To-faktor-kode": ("Two-factor code", "Zwei-Faktor-Code", "Tvåfaktorskod", "Tofaktorkode"),
    "Skriv den 6-cifrede kode fra din autentificeringsapp, eller en gendannelseskode.": (
        "Enter the 6-digit code from your authenticator app, or a recovery code.",
        "Gib den 6-stelligen Code aus deiner Authentifizierungs-App oder einen Wiederherstellungscode ein.",
        "Skriv den 6-siffriga koden från din autentiseringsapp, eller en återställningskod.",
        "Skriv den 6-sifrede koden fra autentiseringsappen din, eller en gjenopprettingskode."),
    "Kode": ("Code", "Code", "Kod", "Kode"),
    "Annullér": ("Cancel", "Abbrechen", "Avbryt", "Avbryt"),
    "Træner": ("Trainer", "Trainer", "Tränare", "Trener"),
    "Administrator": ("Administrator", "Administrator", "Administratör", "Administrator"),
    "ikke angivet": ("not set", "nicht angegeben", "inte angiven", "ikke oppgitt"),
    "(kun en administrator kan ændre den)": ("(only an administrator can change it)", "(nur ein Administrator kann sie ändern)", "(bara en administratör kan ändra den)", "(bare en administrator kan endre den)"),
    "E-mail": ("Email", "E-Mail", "E-post", "E-post"),
    "Hold": ("Team", "Team", "Lag", "Lag"),
    "ingen": ("none", "keines", "inget", "ingen"),
    "Skift adgangskode": ("Change password", "Passwort ändern", "Byt lösenord", "Bytt passord"),
    "Nuværende adgangskode": ("Current password", "Aktuelles Passwort", "Nuvarande lösenord", "Nåværende passord"),
    "Ny adgangskode (mindst 12 tegn)": ("New password (at least 12 characters)", "Neues Passwort (mindestens 12 Zeichen)", "Nytt lösenord (minst 12 tecken)", "Nytt passord (minst 12 tegn)"),
    "Gentag ny adgangskode": ("Repeat new password", "Neues Passwort wiederholen", "Upprepa nytt lösenord", "Gjenta nytt passord"),
    "Husk-enheder": ("Remembered devices", "Gemerkte Geräte", "Ihågkomna enheter", "Husk enheter"),
    "Glem alle enheder": ("Forget all devices", "Alle Geräte vergessen", "Glöm alla enheter", "Glem alle enheter"),
    "Gendannelseskoder": ("Recovery codes", "Wiederherstellungscodes", "Återställningskoder", "Gjenopprettingskoder"),
    "Adgangskode (bekræftelse)": ("Password (confirmation)", "Passwort (Bestätigung)", "Lösenord (bekräftelse)", "Passord (bekreftelse)"),
    "Opret nye koder (gamle ugyldiggøres)": ("Create new codes (old ones become invalid)", "Neue Codes erstellen (alte werden ungültig)", "Skapa nya koder (gamla ogiltigförklaras)", "Opprett nye koder (gamle blir ugyldige)"),
    'Spillere –': ('Players –', 'Spielerinnen –', 'Spelare –', 'Spillere –'),
    '+ Ny spiller': ('+ New player', '+ Neue Spielerin', '+ Ny spelare', '+ Ny spiller'),
    'Navn': ('Name', 'Name', 'Namn', 'Navn'),
    'Fødselsdato': ('Date of birth', 'Geburtsdatum', 'Födelsedatum', 'Fødselsdato'),
    'Kvartal': ('Quarter', 'Quartal', 'Kvartal', 'Kvartal'),
    'Positioner': ('Positions', 'Positionen', 'Positioner', 'Posisjoner'),
    'Niveau': ('Level', 'Niveau', 'Nivå', 'Nivå'),
    'Fod': ('Foot', 'Fuß', 'Fot', 'Fot'),
    'Trøje': ('Shirt', 'Trikot', 'Tröja', 'Drakt'),
    '(inaktiv)': ('(inactive)', '(inaktiv)', '(inaktiv)', '(inaktiv)'),
    'Ret': ('Edit', 'Bearbeiten', 'Ändra', 'Rediger'),
    'Profil': ('Profile', 'Profil', 'Profil', 'Profil'),
    'Ingen spillere endnu.': ('No players yet.', 'Noch keine Spielerinnen.', 'Inga spelare ännu.', 'Ingen spillere ennå.'),
    'Holdets fokus': ('Team focus', 'Teamfokus', 'Lagets fokus', 'Lagets fokus'),
    'ret': ('edit', 'bearbeiten', 'ändra', 'rediger'),
    'Spillerskema': ('Player form', 'Spielerbogen', 'Spelarformulär', 'Spillerskjema'),
    'til tablet/telefon': ('for tablet/phone', 'für Tablet/Handy', 'för surfplatta/telefon', 'for nettbrett/telefon'),
    'niveau, kalender, noter': ('level, calendar, notes', 'Niveau, Kalender, Notizen', 'nivå, kalender, anteckningar', 'nivå, kalender, notater'),
    'Noter': ('Notes', 'Notizen', 'Anteckningar', 'Notater'),
    'del med trænerne': ('share with the trainers', 'mit den Trainern teilen', 'dela med tränarna', 'del med trenerne'),
    'Overblik': ('Overview', 'Überblick', 'Överblick', 'Oversikt'),
    'hele holdet': ('the whole team', 'das ganze Team', 'hela laget', 'hele laget'),
    'Vis fuld version': ('Show full version', 'Vollversion anzeigen', 'Visa fullständig version', 'Vis full versjon'),
    'Opret den første': ('Create the first one', 'Erste anlegen', 'Skapa den första', 'Opprett den første'),
    'Kom i gang': ('Get started', "Los geht's", 'Kom igång', 'Kom i gang'),
    'roller og samlet score': ('roles and total score', 'Rollen und Gesamtwert', 'roller och totalpoäng', 'roller og samlet score'),
    'svar pr. spiller': ('answers per player', 'Antworten pro Spielerin', 'svar per spelare', 'svar per spiller'),
    'alder, fremmøde, trivsel': ('age, attendance, well-being', 'Alter, Anwesenheit, Wohlbefinden', 'ålder, närvaro, trivsel', 'alder, oppmøte, trivsel'),
    'runde for runde': ('round by round', 'Runde für Runde', 'omgång för omgång', 'runde for runde'),
    'roller og færdigheder': ('roles and skills', 'Rollen und Fähigkeiten', 'roller och färdigheter', 'roller og ferdigheter'),
    'én side pr. spiller': ('one page per player', 'eine Seite pro Spielerin', 'en sida per spelare', 'én side per spiller'),
    'Mobilvisning': ('Mobile view', 'Mobilansicht', 'Mobilvy', 'Mobilvisning'),
    'til banen': ('for the pitch', 'für den Platz', 'till planen', 'til banen'),
    'Vis kun de seneste': ('Show only the latest', 'Nur die neuesten anzeigen', 'Visa bara de senaste', 'Vis bare de siste'),
    'lukket': ('closed', 'geschlossen', 'stängd', 'lukket'),
    'åben til': ('open until', 'offen bis', 'öppen till', 'åpen til'),
    'færdige': ('completed', 'fertig', 'klara', 'ferdige'),
    'påbegyndt': ('started', 'begonnen', 'påbörjade', 'påbegynt'),
    'Gem': ('Save', 'Speichern', 'Spara', 'Lagre'),
    'Gem & næste ›': ('Save & next ›', 'Speichern & weiter ›', 'Spara & nästa ›', 'Lagre & neste ›'),
    '‹ Forrige': ('‹ Previous', '‹ Zurück', '‹ Föregående', '‹ Forrige'),
    'Til listen': ('To the list', 'Zur Liste', 'Till listan', 'Til listen'),
    'Ikke vurderet': ('Not rated', 'Nicht bewertet', 'Inte bedömd', 'Ikke vurdert'),
    'Niveauvurdering efter DBU': ('Level assessment (DBU)', 'Niveaubewertung (DBU)', 'Nivåbedömning (DBU)', 'Nivåvurdering (DBU)'),
    'Samlet niveau for spilleren': ('Overall level of the player', 'Gesamtniveau der Spielerin', 'Spelarens samlade nivå', 'Spillerens samlede nivå'),
    '– brug mine valg ovenfor –': ('– use my choices above –', '– meine Auswahl oben verwenden –', '– använd mina val ovan –', '– bruk valgene mine ovenfor –'),
    'Vælg en spiller for at score.': ('Choose a player to score.', 'Wähle eine Spielerin zum Bewerten.', 'Välj en spelare att bedöma.', 'Velg en spiller å score.'),
    'Ingen spillere.': ('No players.', 'Keine Spielerinnen.', 'Inga spelare.', 'Ingen spillere.'),
    'Opret spillere først': ('Create players first', 'Zuerst Spielerinnen anlegen', 'Skapa spelare först', 'Opprett spillere først'),
    'Forklaring': ('Legend', 'Legende', 'Förklaring', 'Forklaring'),
    'Ret farver': ('Edit colours', 'Farben ändern', 'Ändra färger', 'Endre farger'),
    'Gennemsnit vises som en blanding af nabofarverne.': ('Averages are shown as a blend of the neighbouring colours.', 'Durchschnitte werden als Mischung der benachbarten Farben angezeigt.', 'Medelvärden visas som en blandning av grannfärgerna.', 'Gjennomsnitt vises som en blanding av nabofargene.'),
    'Klubadministration': ('Club administration', 'Vereinsverwaltung', 'Klubbadministration', 'Klubbadministrasjon'),
}
TR = {"en": {}, "de": {}, "sv": {}, "no": {}}
for _k, _v in _T.items():
    for _lang, _x in zip(("en", "de", "sv", "no"), _v):
        TR[_lang][_k] = _x


def current():
    c = request.cookies.get(COOKIE) if request else None
    if c in LANGS:
        return c
    u = g.get("user")
    try:
        if u is not None and u["lang"] in LANGS:
            return u["lang"]
    except (KeyError, IndexError):
        pass
    return DEFAULT


def gettext(text):
    return TR.get(current(), {}).get(text, text)
