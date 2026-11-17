# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/da/1.1.0/) · Versionering: [SemVer](https://semver.org/lang/da/).

## [Unreleased]

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
