# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/da/1.1.0/) · Versionering: [SemVer](https://semver.org/lang/da/).

## [Unreleased]

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
