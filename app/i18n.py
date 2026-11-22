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
