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
Åbn `http://<server>:1020` → **Første opsætning** (opretter administrator) → scan QR-kode med en autentificeringsapp → gem gendannelseskoderne.
Derefter: **Administration → Hold** (opret hold) → **Brugere** (opret trænere og tilknyt dem til hold) → **Spillere** (opret spillere).

## Deploy med Dockhand (direkte fra GitHub)
Appen kører på **port 1020** (`U11_PORT`).
1. Push repoet til GitHub (privat anbefales; giv Dockhand adgang med en deploy key eller et token).
2. Dockhand → **Stacks → Ny stack → fra Git repository**: peg på repoet, branch `main`, compose-sti `docker-compose.yml`.
   Dockhand bygger imaget lokalt fra `Dockerfile` – ingen registry nødvendig.
3. Miljøvariabler i stacken: `SECRET_KEY` (valgfri, ellers genereres og gemmes i volumen), `COOKIE_SECURE=1` hvis du bruger HTTPS, evt. `SETUP_TOKEN`. `U11_PORT` er 1020 som standard.
4. Deploy → åbn `http://<server>:1020`.
5. Opdatering: `scripts/release.sh X.Y.Z` → `git push && git push --tags` → **Redeploy / pull** i Dockhand.
Alternativ: sæt `U11_IMAGE=ghcr.io/<bruger>/u11-udvikling:<version>` for at bruge det image, som GitHub Actions udgiver.

## Klubprofil
**Administration → Klubprofil**: klubnavn, adresse/kontakt, hjemmeside, fodtekst på rapporter, primær farve og logo (PNG/JPEG/WebP, maks. 512 kB). Vises i header, på loginsiden og på rapporterne.
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
