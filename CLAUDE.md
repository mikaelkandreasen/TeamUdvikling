# CLAUDE.md – orientering til Claude (og andre udviklere)

Læs denne fil først, derefter `BACKLOG.md` (hvad der skal laves) og `docs/ARCHITECTURE.md` (hvordan det hænger sammen).

## Hvad er projektet?
**Team Udvikling** (repo: u11-udvikling; navnet kan ændres under Klubprofil) er en selvhostet webapp (Flask + SQLite) til trænere på børnehold. Den erstatter en Excel-model og samler:
- **Evaluering** af spillere på DBU's 4 roller (boldholder, medspiller, presspiller, støttespiller) × 6 nøglefærdigheder
  (teknik, bevægelse, scanning, timing, positionering, maskering) = 24 kriterier, scoret 1–5, i 4 runder, af flere trænere.
- **Teamoversigt** (rolle-gennemsnit, samlet, enighed mellem trænere), **udvikling**, **position/bane**, **områder**, **spillerprofil** (radar).
- **Motivation og træningsønsker** (3 kategorier, 22 pladser, spillervisning til tablet).
- **Udviklingsdata**: relativ alder (fødselskvartal), fremmøde, kampdeltagelse, trivsel, motorik, handleplan.
- **Spillerrapport** (A4-print) pr. spiller. **Flere hold** med separate trænerlogins. **Login med adgangskode + TOTP-2FA.**

Brugeren (træner for et U11-pigehold) driver den på en hjemmeserver via Docker/Dockhand. UI og tekster er på **dansk**.

## Kør og test
```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
python3 -m pytest -q                      # alle tests skal være grønne før commit
U11_DATA_DIR=./data flask --app wsgi run --debug   # lokal udvikling på http://127.0.0.1:5000 (første besøg: /setup)
docker compose up --build                 # kør som container (se README.md)
```
Der må ikke indlæses spillerdata i repoet, testene eller seed-scripts. Testdata skal være opdigtede (fx "Anna Alfa").

## Arkitektur i korte træk
`app/__init__.py` (create_app, CSRF, sikkerhedsheadere) · `auth.py` (login/2FA/lockout/gate) · `teams.py` (hold-adgang) ·
`db.py` (skema, backup, indstillinger) · `model.py` (roller, kriterier, ALLE beregninger – rene funktioner) ·
`evaluation.py`, `motivation.py`, `devdata.py`, `reports.py`, `players.py`, `admin.py`, `views.py` (blueprints) ·
`activity.py` (aktive nu, brugsstatistik) · `formations.py` (opstillinger, positionsmatch, holdforslag) · `lineup.py` (holdsætning) · `photos.py` (billedbehandling) · `charts.py` (server-SVG) · `templates/` · `static/` · `tests/`.

## Regler der IKKE må brydes
1. **Hold-afgrænsning.** Al adgang til spillerdata skal gå via `helpers.get_player()` / `helpers.active_players()` /
   `model.load_rounds(db, team_id())` eller en SQL med `players.team_id = ?`. Nye forespørgsler, der rører spillere,
   evalueringer, svar eller udviklingsdata, skal afgrænses til `g.team`. Tilføj altid en isolationstest i `tests/test_teams.py`.
2. **Ingen indlejret JavaScript eller `on*=`-handlers** (CSP tillader kun scripts fra 'self'). Brug `static/app.js` med `data-*`-attributter.
3. **Alle POST-formularer indeholder CSRF-token** (`{{ csrf() }}` eller `<input name="csrf_token" ...>`).
4. **Nye endpoints er låst som standard** (global `gate()` i `auth.py`). Gør kun noget offentligt via `PUBLIC` – og kun med god grund.
5. **Admin-sider** ligger i `admin.py` (blueprint er beskyttet af `admin_required`). Trænere må ikke kunne slette spillere, eksportere eller administrere brugere.
6. **Skemaændringer**: øg `SCHEMA_VERSION` i `db.py` og tilføj en migration (idempotent). Slet aldrig brugerdata i en migration uden backup.
7. **Aldrig hemmeligheder, databaser eller `.env` i git.** Revisionsloggen må ikke indeholde scores eller adgangskoder.
8. **Beregninger** (samlet, enighed, relativ alder, tolkningstekster) ligger i `model.py`/`devdata.py` og skal have enhedstests, når de ændres.
9. **Mobile-first**: alt skal kunne bruges på en 360–430 px bred telefon (min. 44–48 px trykflader). Tjek nye sider i det format.

## Arbejdsgang (versionsstyring)
- Én gren pr. opgave: `feat/<kort-navn>`, `fix/<kort-navn>`; merge til `main` via pull request (eller fast-forward, hvis du arbejder alene).
- **Conventional Commits** på dansk eller engelsk: `feat(evaluation): …`, `fix(auth): …`, `docs: …`, `test: …`, `chore: …`, `refactor: …`.
- Opdatér **`CHANGELOG.md`** under `## [Unreleased]` for alt brugersynligt. Opdatér **`BACKLOG.md`** (flyt punktet til "Færdigt", tilføj nye opdagede opgaver).
- **SemVer**: `0.x` indtil første rigtige brug i drift. Nye funktioner = minor, rettelser = patch, brud på data/URL'er = major (eller minor før 1.0).
- Udgiv med `scripts/release.sh X.Y.Z` (kører tests, opdaterer `VERSION` + `CHANGELOG`, committer, opretter tag `vX.Y.Z`).
  Push `main` og tags → GitHub Actions bygger og udgiver Docker-imaget til GHCR (`ghcr.io/<bruger>/u11-udvikling:X.Y.Z`).
- Definition of done: tests grønne, ny adfærd testet, CHANGELOG + BACKLOG opdateret, mobilvisning tjekket, ingen spillerdata i repoet.

## Når du overtager arbejdet i en ny Claude-session
1. `git log --oneline -15` og `git status` – hvad er sket sidst?
2. Læs `BACKLOG.md` – tag øverste uafsluttede punkt i "Næste", medmindre brugeren siger andet.
3. Kør `python3 -m pytest -q` for at bekræfte udgangspunktet.
4. Lav en kort plan, arbejd i små commits, hold CHANGELOG/BACKLOG opdateret, og afslut med tests + en kort status til brugeren.
5. Skriv beslutninger der ikke er oplagte ind i `docs/DECISIONS.md` (kort: kontekst, valg, konsekvens).

## Kendte begrænsninger i v0.1.0
- Docker-image og CI er skrevet, men ikke kørt i det miljø, hvor første version blev bygget (ingen netværk/daemon) – verificér ved første `docker compose up --build`.
- QR-koden til 2FA kræver pakken `qrcode` (er i `requirements.txt`); uden den vises kun den manuelle nøgle.
- Excel-importen fra den gamle model er bevidst udeladt (ingen spillerdata i første version).
