# Backlog

Prioriteret liste. Øverst = næste. Format: `ID · titel · størrelse (S/M/L) – accept (hvordan vi ved, den er færdig)`.
Opdatér ved hver ændring: flyt færdige punkter til "Færdigt" og tilføj nye opdagelser nederst i "Idéer".

## Næste (P0 – før første rigtige brug)
(ingen åbne)

## Senere (P1)
- ~~B-014 · Trivsel og motivation over tid~~ (færdig i v0.22.0) – · M – flere målinger (datoer) i stedet for én værdi; linjediagram i rapporten.

- ~~B-021 · DBU KampKlar-integration~~ – dækket af holdets iCal-kalender og kampforslag (v0.26.0); ingen scraping af mit.dbu.dk.

- **B-022 · Ekstern pentest/scan af udrullet system** · S – OWASP ZAP/nuclei mod HTTPS-adressen, før den åbnes på internettet. *Status: Kommandoer til ZAP/nuclei i docs/DRIFT.md – selve scanningen udføres af dig.*

> Bemærk: Administration → Backlog i appen er en separat, redigerbar liste i databasen. Denne fil er udviklerens reference; hold dem i takt ved større ændringer.

## Teknisk gæld og forbedringer (P1)
- **B-046 · Off-site-backup og afprøvet gendannelse** · S (drift, din opgave) – restic/rclone crypt til ekstern placering, `BACKUP_OFFSITE=1` (A1/A12, se docs/ARKITEKTURGENNEMGANG.md).
- **B-047 · Nøgler som miljøvariabler og lukket port** · S (drift) – `SECRET_KEY`/`TOTP_KEY` i Dockhand, `TEAMUDVIKLING_BIND=127.0.0.1` eller ingen `ports:` (A2/A3).
- **B-049 · Overvågning og fast image-version** · S – Uptime Kuma mod /healthz, `TEAMUDVIKLING_IMAGE` med fast version, Dependabot, låste hashes (A9/A11).

## Idéer (uprioriteret)
- **I-11** Token-beskyttet, skrivebeskyttet download-adresse til seneste backup, så et eksternt job kan hente den over HTTPS uden adgang til volumen.
- **I-12** Mørkt udseende: tilpas de sidste inline-farvede bokse (gule/blå noter) og vælg udseende også under Min konto (gemmes pr. bruger).

## Færdigt
- [x] **B-004** Backup-restore afprøvet og bekræftet af dig (lukket).
- [x] Position og bane: spillere ligger ikke længere oven på hinanden (v0.38.1).
- [x] **B-12** Backup hentet fra siden har dato og tid i filnavnet (`teamudvikling-2026-11-23_1142.db`) (v0.38.0).
- [x] **B-13** Planlagt automatisk backup: systemadministrator vælger ugedage, klokkeslæt og antal; `latest.db` + `latest.json` efter hver backup til eksterne hentejobs; status og næste kørsel vises (v0.38.0). Samtidig rettet: to backups i samme sekund kunne slettes ved oprydning.
- [x] **v0.37.0** – Mørkt udseende (Auto/Lyst/Mørkt) og besked til alle sendes også til afsenderen.
- [x] **v0.36.0** – Gendan backup via siden.
- [x] **B-01** Første gennemløb med trænere – udført af dig; nye ønsker er løbende lagt ind (lukket).
- [x] **B-04** CI/GHCR-udgivelse bekræftet af dig (lukket).
- [x] **B-07** Cloudflare Access og rate-limit-regler – lavet af dig (lukket).
- [x] **B-11** PNG/WebP afvises ved flere end 16 mio. pixels (JPEG 40 mio.); `admin.py` delt i `admin.py` + `admin_more.py` (v0.34.0).
- Fjernet uden at blive lavet: gammel B-042b (egne roller/færdigheder), gammel B-041c (repository-lag) og idéerne tilmelding/afbud, forældrelink, spillerbillede-bulk og rapport som billede.
- [x] **I-01** Fremmøde kobles til kampe: fraværende tæller ikke som bænk/«lidt tid» (v0.34.0).
- [x] **I-05** Tjek mod lækkede adgangskoder var lavet, men slået fra – tændt som standard i compose (v0.34.0).
- [x] **I-06** Rolle, e-mail, slet, lås op og profiler kræver frisk 2FA-kode (v0.34.0).
- [x] **I-07** Tilgængelighedstests (kontrast, labels, alt, trykflader); fandt og rettede manglende labels på Min konto (v0.34.0). Browser-test med Playwright er forberedt, men kræver installation.
- [x] **I-09** Evalueringsskemaet (v0.34.0) og noter (v0.35.0) gemmer uden sideskift.
- [x] **B-09 / B-045** Resten af skabelonerne og flash-beskeder er oversat til en/de/sv/no (v0.35.0). Maskinoversat – bør læses af modersmålstalende; sysadmin-sider og Python-fejltekster med variable er på dansk.
- [x] **B-08** Lukket.
- [x] **I-10** Kalenderændringer (flyttet/væk) vises for oprettede kampe, med knap til at opdatere (v0.34.0).
- [x] **B-051** Assistenter låst ude af motivation, udviklingsdata, rapporter, kampe og holdsætning på serversiden (v0.33.1).
- **Arkitekturgennemgang + komplet dokumentation** – færdig (v0.30.0): driftstjek, tokens fjernet fra log, backup uden login, docs/ARCHITECTURE, SWIMLANES, FUNKTIONER, ARKITEKTURGENNEMGANG.
- **Testmail-knap og Excel-import** – var allerede lavet (Administration); fjernet fra idéer.
- **Sprogvalg (da/en/de/sv/no)** – grundlag færdigt (v0.27.0): menuer, login, menu og Min konto oversat; resten under B-045.
- **B-041b · SQL-afgrænsning kontrolleres automatisk** – færdig (v0.27.0): `tests/test_sql_scope.py` + `sql_scope_allow.txt`.
- **B-042a · Kriterietekster i tabel** – færdig (v0.27.0), migration 013.
- **B-043 · Delvise opdateringer** – færdig (v0.27.0) som eget `data-swap`-script (D-028). Idé: udvid til evalueringsskema og noter.
- **Opstillingsforslag med prioritet på hvide pletter** – færdig (v0.27.0).
- **Kampforslag fra iCal-link** – færdig (v0.26.0). Idé: vis ændringer (flyttet/aflyst) for allerede oprettede kampe ved næste hentning.
- **B-044 · E-mail-kø** – færdig (v0.26.0). Nulstillingsmail og prøvemail sendes stadig direkte, så brugeren får fejl med det samme (D-026).
- **v0.26.0** – B-041 automatisk isolationstest af alle id-ruter (andet hold og anden klub, positiv kontrol, fejler ved ny ubeskyttet rute).
- **v0.25.0** – B-040 rigtige migrationer (runner, log, backup før, rollback, tests, docs/MIGRATIONS.md).
- **v0.23.0** – Kampe: spillere på positioner pr. periode, spilletid og hvide pletter pr. spiller/position over tid.
- **v0.22.0** – Forældrerapporter for hele holdet, svar på beskeder + læst-status, motivation over tid (B-014 færdig), forældresamtaler med hjemmeøvelse.
- **v0.21.0** – Holdets træningsfokus kan vælges (op til 4 punkter ud fra forslag + eget) og vises på Hjem og forældrerapporter; B-018 blokeringslog i administration (Sikkerhedslog) var allerede på plads og lukkes.
- **v0.20.x** – Indbakke: klubadministrator → klub, chef-træner → hold, systemadministrator → alle; vises ved login, ✉ i topbjælken, valgfri e-mail.
- **v0.19.x** – Tal-fri forældrerapport med logo, klubmotto, holdslogan og maskotbillede; klubmotto på loginsiden (husket enhed).
- **v0.18.x** – Navngivne evalueringsrunder, lukning efter 30 dage (genåbning), kun færdige runder i profilen, stoppede trænere beholder evalueringer, holdskifte med historik, nye scorefarver, niveau ud fra samlet score.
- **v0.17.0** – Skjulte links uden adgang, Hold + Noter på Hjem, wiki-noter.
- **v0.16.0** – DBU-vurdering af 10 kompetencer (A–D, alle A = A+).
- **v0.13–v0.15** – Niveau pr. træner (A+…Nystartet), automatisk 25/50/25-fordeling med justerbare andele, flere profiler pr. bruger.
- **B-011/B-012/B-015/B-016** – assistent (skrivebeskyttet), sæsonskifte, fremmøde pr. træning/kamp og tokenbaseret spillerlink er færdige.
- **v0.12.0** – B-013 kriterietekster pr. hold, B-017 2FA-hærdning, B-023 kryptering af TOTP-hemmeligheder, B-020/B-024 opbevaringspolitik og automatisk sletning, B-018 sikkerhedslog, kalender via iCal (kamptider uden DBU-scraping), testmail, valgfri tjek af lækkede adgangskoder, 2FA-kode til nulstillinger, brugeroversigt med detaljeside, træningsfokus, «siden sidste runde», print af opstilling, PWA-manifest. Afvist: B-019 server-PDF (browserens «gem som PDF» dækker behovet, jf. D-016), B-031 login pr. klub (strider mod neutral loginside, D-014).
- **v0.11.0** – B-004 backup/restore (kontrol + vejledning), B-030 CI-røgtest, B-003/B-022 tjeklister (docs/DRIFT.md), B-012 sæsonskifte, B-015 fremmøde pr. træning/kamp, B-014 trivsel over tid (motivation over tid mangler), B-011 assistent med læseadgang, B-016 spillerlink.
- **B-001** – Docker-build og Dockhand-deploy kører i drift på hjemmeserveren (CI/GHCR-udgivelse er stadig uverificeret – se B-030).
- **B-002** – HTTPS via Cloudflare Tunnel (`COOKIE_SECURE=1`, `__Host-`-cookies, ProxyFix).
- **B-010** – Holdadministratorer: klubadministrator og chef-træner (v0.9.0/v0.10.0), med isolationstests.
- **v0.10.0** – Holdindstillinger og funktionsvalg, chef-trænere (+ invitation), spillerniveau, holdnoter, slogan/mascot med rapport, deling i op til 9 A/B/C-hold, brugernavn-tjek, sysadmin-brugeroversigt, op til 20 evalueringsrunder.
- **v0.1.0** – Første version: flere hold med separate trænerlogins, login + obligatorisk TOTP-2FA (gendannelseskoder, lockout), 4 roller × 6 nøglefærdigheder × 4 runder × flere trænere, teamoversigt (enighed), udvikling, position & bane, områder, spillerprofil (radar), motivation (22 spørgsmål, tablet-visning), udviklingsdata (relativ alder, fremmøde, trivsel, motorik, handleplan), spillerrapport (A4), mobilforside + bundmenu, admin (hold, brugere, runder, backup, Excel-eksport, revisionslog), Docker + CI + versionsstyring. Ingen spillerdata medfølger.
