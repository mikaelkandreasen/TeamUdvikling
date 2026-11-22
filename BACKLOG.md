# Backlog

Prioriteret liste. Øverst = næste. Format: `ID · titel · størrelse (S/M/L) – accept (hvordan vi ved, den er færdig)`.
Opdatér ved hver ændring: flyt færdige punkter til "Færdigt" og tilføj nye opdagelser nederst i "Idéer".

## Næste (P0 – før første rigtige brug)
- **B-003 · Første rigtige gennemløb med trænere** · M – 1 hold, 2 trænere, 1 evalueringsrunde, motivationsskema på tablet; liste over friktionspunkter → nye backlog-punkter. *Status: Tjekliste i docs/DRIFT.md – selve gennemløbet udføres af dig.*
- **B-004 · Backup-restore afprøvet** · S – `scripts/restore.sh` testet mod en rigtig backup; beskrivelse af off-site kopi (fx rsync/rclone af volumen). *Status: Backup kontrolleres automatisk; scripts/restore.sh + verify-backup.py; docs/BACKUP.md (off-site med rclone/rsync).*

## Senere (P1)
- ~~B-014 · Trivsel og motivation over tid~~ (færdig i v0.22.0) – · M – flere målinger (datoer) i stedet for én værdi; linjediagram i rapporten.

- ~~B-021 · DBU KampKlar-integration~~ – dækket af holdets iCal-kalender og kampforslag (v0.26.0); ingen scraping af mit.dbu.dk.

- **B-022 · Ekstern pentest/scan af udrullet system** · S – OWASP ZAP/nuclei mod HTTPS-adressen, før den åbnes på internettet. *Status: Kommandoer til ZAP/nuclei i docs/DRIFT.md – selve scanningen udføres af dig.*

> Bemærk: Administration → Backlog i appen er en separat, redigerbar liste i databasen. Denne fil er udviklerens reference; hold dem i takt ved større ændringer.

- **B-030 · Verificér CI/GHCR-udgivelse af Docker-image ved tag** · S – push af `vX.Y.Z` bygger og udgiver image til GHCR; Dockhand kan trække det. *Status: CI har røgtest af Docker-imaget før udgivelse; docs/DRIFT.md beskriver verificering af GHCR/Dockhand. Resterer: din første kørsel af workflowet.*

## Teknisk gæld og forbedringer (P1)
- **B-041c · Flyt rå SQL ind i et repository-lag** · M – de 68 gennemgåede forespørgsler på spillerdata samles i få funktioner (`access.py`), så afgrænsningen sker ét sted. Ratchet-testen (B-041b) forhindrer nye huller imens. *Vurdering: lav gevinst pr. indsats, så længe rutetesten og ratchet-testen fanger huller; tages, hvis ratchet-listen begynder at vokse.*
- **B-042b · Hold med egne roller/færdigheder** · L – restpunkt af B-042: antal og navne på roller og nøglefærdigheder pr. hold (i dag fast 4 × 6 = 24 i `model.py`; beregninger, diagram, niveauer og rapporter bruger fast indeks 0–23). Kræver generalisering af `model.py`/`levels.py`/`charts` og migrering af `evaluations.crit`. Tabel til holdets tekster og adgangsfunktion findes (B-042a). *Plan: (1) tabeller `crit_roles/crit_skills` pr. hold med standardsæt, (2) `model.py`-funktioner tager en kriteriestruktur i stedet for konstanter, (3) `evaluations.crit` bliver nøgle til kriterie-id, (4) diagrammer/niveauer/rapport læser antal fra strukturen, (5) UI til at redigere. Bør laves som egen session med omfattende regressionstest, fordi alle beregninger berøres.*

- **B-045 · Oversæt resten af appen** · L – markér resten af skabelonerne (≈85 filer) og beskeder fra Python-koden med `_()`, oversæt til en/de/sv/no, og få oversættelserne læst igennem af modersmålstalende. Tilføj dato-/tegnformat pr. sprog hvis nødvendigt. *Status v0.28.0: menuer, login, Menu, Min konto, Hjem, spillerliste og evalueringsknapper er oversat; resten (især sætninger med fed tekst/links midt i, som skal skrives som hele sætninger) mangler.*

## Idéer (uprioriteret)
- Forslag til næste kamps opstilling, der automatisk prioriterer hvide pletter og lav spilletid.
- Fremmøde kobles til kampe, så spillere der ikke var med ikke tæller som bænk.
- Kalender med tilmelding/afbud og påmindelser (Spond-lignende).
- Forældrelink uden login til barnets rapport (kræver beslutning om samtykke).
- Spillerbilleder: bulk-upload og automatisk sletning når samtykke trækkes tilbage.
- Ekstern scanning (ZAP/nuclei) af den rigtige adresse bag Cloudflare, når siden er oplagt (supplerer den lokale simulation).
- Tjek af adgangskoder mod lækkede lister (k-anonymitet) ved oprettelse/skift.
- Mulighed for at kræve admin-2FA-kode også til de direkte «Nulstil»-knapper (midlertidig kode).
- Playwright-/UI-tests af mobil-flowet; tilgængelighedstjek (kontrast, skærmlæser).
- Eksport af rapport som billede til deling med forældre.

## Færdigt
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
