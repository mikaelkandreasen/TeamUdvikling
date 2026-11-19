# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/da/1.1.0/) · Versionering: [SemVer](https://semver.org/lang/da/).

## [Unreleased]

## [0.7.1] - 2026-11-19

## [0.7.0] - 2026-11-19

### Tilføjet
- **Op til 4 positioner pr. spiller** med dropdowns (grupperet: Målmand, Forsvar, Midtbane, Kant, Angreb, Andet). Nye positioner: **Højre kant / Venstre kant**, Højre/Venstre back, Midtstopper, Defensiv/Offensiv midtbane. Position & bane viser Valg 1–4. Import/eksport har kolonnerne Position 3 og 4.
- **Holdsætning** (menu): opstillinger for 3v3, 5v5, 8v8 og 11v11 med flere spillesystemer pr. kamptype (fx 3-3-1, 2-3-2, 4-3-3, 4-4-2). Dropdown pr. plads, bænk, flere gemte opstillinger, ét **idealhold** pr. kamptype, og «Foreslå hold» ud fra spillernes positioner (valgfrit også ud fra scores). Forslag gemmes først ved «Gem».
- **Spillerbilleder** (kræver markeret forældresamtykke): beskæres kvadratisk, genkodes til JPEG, metadata/GPS fjernes. Vises som mini på Position & bane, Holdsætning, spillerlisten, profil og rapport. Slettes sammen med spilleren; indgår i backup og JSON-eksport.

### Ændret
- **Systemet hedder nu «Team Udvikling»** (før «U11 Udvikling») overalt: header, fanetitel, fodlinje, 2FA-appen og e-mails. Navnet kan ændres under Administration → Klubprofil → «Systemets navn».
- Skema v6 (`players.position3/4`, `player_photos`, `lineups`, `lineup_slots`; idempotent). Ny afhængighed: Pillow.

## [0.6.1] - 2026-11-19

### Sikkerhed
- Simuleret angreb på login bag Cloudflare (`tests/test_login_attack.py`, 25 angreb). Rettet: lås-DoS (kontolåsning er nu pr. bruger+IP, global grænse 25 fejl), brugeropremsning via svartid på låste konti, session-cookie der virkede efter log ud, samtidig genbrug af 2FA-kode, indeksering og versionsvisning på login-siden, grænse for inputlængde, advarsel ved `COOKIE_SECURE` uden `TRUSTED_PROXIES`. Se docs/SECURITY.md (inkl. Cloudflare-indstillinger).
- Skema v5 (`login_fails`, `revoked_sessions`; idempotent). Eksisterende sessioner logges ud én gang ved opdatering (husk-enheder virker stadig).

## [0.6.0] - 2026-11-19

### Tilføjet
- **E-mailadresse på brugere** (Administration → Brugere; vises skrivebeskyttet under Min konto).
- **Nulstilling af adgangskode eller 2FA via e-mail, efter administrators godkendelse med egen 2FA-kode.** Engangslink (60 min., maks. 3 pr. time). 2FA-nulstilling kræver også brugerens adgangskode, så e-mail alene aldrig omgår 2FA. Opsættes med `PUBLIC_URL` og `SMTP_*` (se README); uden dem er funktionen skjult.

### Ændret
- Skema v4 (`users.email`, `reset_tokens`; idempotent migration, ingen data slettes).

## [0.5.0] - 2026-11-18

### Tilføjet
- **Husk denne enhed i 30 dage** (flueben ved 2FA-login): logger ind uden adgangskode/2FA på den enhed. Fast udløb, roterende token med tyveridetektion, tilbagekaldes ved log ud/adgangskodeskift/2FA-nulstilling/«Glem alle enheder» (Min konto). Administration kræver stadig frisk login med kode. `REMEMBER_DAYS` (0 = fra).

## [0.4.0] - 2026-11-18

### Tilføjet
- **Backlog i Administration** med prioritet (P0–Idé), status, flyt op/ned og redigering; startliste følger med.
- **Evalueringsrunder pr. hold** (2–8, standard 4): tilføj runde, fjern sidste runde (sletter dens evalueringer) og slet scores pr. runde/træner/spiller (Administration → Evalueringer).
- **Se siden som træner**: administrator kan se præcis, hvad en bestemt træner ser (skrivebeskyttet, kun trænerens hold). Afsluttes med knap i banneret.
- Tydeligere valg af flere hold til en træner (funktionen fandtes allerede og er nu dækket af tests).

## [0.3.0] - 2026-11-18

### Tilføjet
- **Import af spillere og hold** (Administration → Import) fra Excel (.xlsx) eller CSV: skabelon, validering, forhåndsvisning før noget gemmes, nye hold oprettes, eksisterende spillere (hold + navn + fødselsdato) opdateres. Formler køres aldrig, filer gemmes ikke, revisionsloggen får kun antal.

## [0.2.3] - 2026-11-18

### Rettet
- Dockhand kan ikke bygge fra Git (skrivebeskyttet filsystem). `compose.yaml` henter nu det færdige image fra GHCR; `compose.build.yaml` bruges til lokal bygning. CI udgiver `latest` ved push til `main`, og sikkerhedsjobbet blokerer ikke længere udgivelsen.

## [0.2.2] - 2026-11-18

### Ændret
- `docker-compose.yml` hedder nu `compose.yaml` (Dockhands standardsti): en Git-stack kan oprettes uden yderligere indstillinger.

## [0.2.1] - 2026-11-17

### Sikkerhed
- **Kritisk:** første opsætning kræver nu altid en engangskode (genereres automatisk, vises i log/`/data/setup_token`, slettes efter brug).
- Login-spærre pr. IP (429), `TRUSTED_PROXIES` til korrekt klient-IP bag reverse proxy.
- Sessioner bindes til adgangskoden (stjålne cookies dør ved skift); nulstilling af 2FA afbryder aktive sessioner.
- Excel-eksport neutraliserer formler; gendannelseskoder 48 bit med nøglet hash; strengere `next`-validering.
- HSTS, Permissions-Policy, COOP/CORP, `__Host-`-cookie ved HTTPS; `/healthz` viser ikke version.
- Compose: `pids_limit`, `mem_limit`, valgfri `U11_BIND`; gunicorn-grænser; fastlåste afhængigheder; Dependabot, `pip-audit` og `bandit` i CI.
- Pentest som regressionstests (`tests/test_security.py`) og `docs/SECURITY.md`.

### GDPR
- Offentlig side `/privatliv`, admin-side *Dataoprydning* (slet inaktive spillere), audit-log slettes efter 12 mdr., `docs/GDPR.md` (dataregister, rettigheder, DPIA, brud).

## [0.2.0] - 2026-11-17

### Tilføjet
- Klubprofil (admin): klubnavn, kontaktinfo, fodtekst, primær farve (kontrastkontrol) og logo (indholdstjek, SVG afvist). Vises i header, login og rapporter.

### Ændret
- Standardport er nu **1020**; `docker-compose.yml` bygger direkte fra Git i Dockhand (image valgfrit via `U11_IMAGE`).

## [0.1.0] - 2026-11-17

### Tilføjet
- Flere hold med separate trænerlogins; trænere ser kun de hold, de er tildelt; administratorer ser alle. Holdskifter i headeren.
- Login med adgangskode + obligatorisk TOTP-2FA (RFC 6238), gendannelseskoder, kontolåsning, replay-beskyttelse, tvungent skift af midlertidig adgangskode, CSRF, CSP og sikkerhedsheadere.
- Evaluering: 4 runder × flere trænere × 24 kriterier (DBU's 4 roller × 6 nøglefærdigheder), scoreformular optimeret til mobil.
- Teamoversigt med rolle-gennemsnit, samlet score, enighed mellem trænere og fortolkning.
- Udvikling pr. runde, position & bane (primær/sekundær), områdeudvikling, spillerprofil med radardiagram, styrker og udviklingsområder.
- Motivation og træningsønsker: 3 kategorier / 22 pladser (blanke kan tages i brug), matrix-input, spillervisning til tablet/telefon, rapport.
- Udviklingsdata: relativ alder (kvartal), fremmøde, kampdeltagelse, trivsel, motorik og handleplan; holdoverblik for relativ alder.
- Spillerrapport (A4-print) pr. spiller og for alle spillere.
- Mobilforside (`/m`), bundmenu og responsive tabeller; auto-redirect til mobilforsiden på telefoner.
- Administration: hold, brugere, runder, automatisk daglig backup, hentning af backup, Excel-eksport, revisionslog, GDPR-indsigt (JSON) og sletning pr. spiller.
- Docker-image, `docker-compose.yml`, GitHub Actions (tests + udgivelse af image), `scripts/release.sh`, `scripts/restore.sh`.
- Dokumentation: `README.md`, `CLAUDE.md`, `BACKLOG.md`, `docs/ARCHITECTURE.md`.

### Bevidst udeladt
- Ingen spillerdata fra den gamle Excel-model; databasen starter tom.
