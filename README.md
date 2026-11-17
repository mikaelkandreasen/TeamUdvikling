# U11 Udvikling

Selvhostet webapp til spillerudvikling på børnehold: DBU's 4 spillerroller × 6 nøglefærdigheder, motivation og træningsønsker, relativ alder,
fremmøde, trivsel, motorik, handleplan og en rapportside pr. spiller. Flere hold og flere trænere, login med 2FA, mobil-venlig.

> Databasen starter **tom** – der følger ingen spillerdata med.

## Kom i gang (Docker)
```bash
git clone https://github.com/<DIT-BRUGERNAVN>/u11-udvikling.git && cd u11-udvikling
cp .env.example .env            # ret SECRET_KEY m.m.
docker compose up -d --build
```
Åbn `http://<server>:8080` → **Første opsætning** (opretter administrator) → scan QR-kode med en autentificeringsapp → gem gendannelseskoderne.
Derefter: **Administration → Hold** (opret hold) → **Brugere** (opret trænere og tilknyt dem til hold) → **Spillere** (opret spillere).

## Deploy med Dockhand
Dockhand styrer en compose-stack. To veje:
1. **Fra GHCR-imaget (anbefalet):** push et tag (`v0.1.0`) → GitHub Actions udgiver `ghcr.io/<bruger>/u11-udvikling:0.1.0`. Opret en stack i Dockhand med
   indholdet af `docker-compose.yml`, sæt `U11_IMAGE`, `SECRET_KEY`, `COOKIE_SECURE`, `U11_PORT` som miljøvariabler, og deploy. Opdatering = vælg nyt tag → redeploy.
   (Er pakken privat, skal Dockhand/serveren logge ind på `ghcr.io` med et token med `read:packages`.)
2. **Fra Git:** hvis din Dockhand-version kan deploye en stack direkte fra et Git-repo, peg på dette repo og `docker-compose.yml` (bygger imaget lokalt).
Persistente data ligger i volumen `u11-data` (`/data`): `u11.db`, `backups/` (automatisk, maks. én pr. døgn, 14 gemmes) og `secret_key`.

## Opdatering, backup og gendannelse
- Opdatér: ny version → `docker compose pull && docker compose up -d` (eller redeploy i Dockhand). Databasen migreres automatisk ved start.
- Backup: *Administration → Hent backup*, eller kopiér `/data/backups`. Gem også kopier uden for serveren.
- Gendan: stop containeren → `scripts/restore.sh u11-backup.db` → start igen.

## Sikkerhed og persondata (børn)
- Brug kun appen på dit lokale netværk/VPN, eller bag HTTPS via en reverse proxy (sæt da `COOKIE_SECURE=1`). Udsæt den ikke direkte på internettet uden HTTPS.
- 2FA er obligatorisk for alle. Trænere ser kun de hold, de er tilknyttet. Administratorer ser alt og kan slette/eksportere data.
- Registrér kun det nødvendige, informér forældrene om formålet, og slet data, når de ikke længere bruges (*Ret spiller → Slet*). Indsigt: *Hent alle data (JSON)*.

## Udvikling
```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
python3 -m pytest -q
U11_DATA_DIR=./data flask --app wsgi run --debug
```
Versionsstyring, backlog og vejledning til videre arbejde (også i en anden Claude-session): se `CLAUDE.md`, `BACKLOG.md`, `CHANGELOG.md`, `docs/`.
Udgiv ny version: `scripts/release.sh 0.2.0 && git push && git push --tags`.
