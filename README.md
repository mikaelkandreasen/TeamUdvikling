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

## Deploy med Dockhand (tilføj stack og kør)
Dockhand bygger ikke selv images. GitHub Actions bygger imaget ved hvert push til `main` og lægger det på `ghcr.io/mikaelkandreasen/u11-udvikling:latest`; stacken henter det.
**Engangsopsætning:** efter første vellykkede kørsel af workflowet (fanen *Actions* på GitHub) skal pakken gøres offentlig, ellers kan Dockhand ikke hente den: GitHub → din profil → *Packages* → `u11-udvikling` → *Package settings* → *Change visibility* → Public.
1. Dockhand → **Stacks → Ny stack → Git repository**: `https://github.com/mikaelkandreasen/TeamUdvikling`, branch `main` (compose-filen `compose.yaml` er standardstien).
2. Tryk **Deploy**. Ingen miljøvariabler er nødvendige: port **1020**, database og nøgle oprettes automatisk i volumen `u11-data`.
3. Åbn `http://<server>:1020`. Første opsætning kræver en engangskode fra containerens log (og `/data/setup_token`). Opret administrator og scan 2FA-koden.
Opdatering: push til `main` (eller tag) → vent på grøn workflow → **Redeploy** i Dockhand (vælg at hente nyeste image).
Privat pakke i stedet: giv Dockhand et GitHub-token med `read:packages` under *Registries*.
Lokal bygning uden Dockhand: `docker compose -f compose.yaml -f compose.build.yaml up --build`.
Persistente data ligger i volumen `u11-data`: `u11.db`, `backups/`, `secret_key` og `branding/`.

## Internet og sikkerhed
Kør kun bag HTTPS-reverse proxy med `COOKIE_SECURE=1` og `TRUSTED_PROXIES=1`; helst bag VPN/Cloudflare Access, da der er børnedata. Se **docs/SECURITY.md** (checkliste) og **docs/GDPR.md**. Første opsætning kræver en engangskode, som står i container-loggen (`docker logs u11-udvikling`) og i `/data/setup_token`.

## Husk enhed
Ved login kan brugeren sætte flueben i "Husk denne enhed i 30 dage". Administration kræver dog altid frisk login med kode. Funktionen kan slås fra med `REMEMBER_DAYS=0`. Se docs/SECURITY.md.

## E-mail og nulstilling af adgangskode/2FA
Administrator kan give hver bruger en e-mailadresse (Administration → Brugere). Er e-mail sat op, kan administratoren trykke **Godkend og send e-mail** (kræver administratorens egen 2FA-kode) for at sende et engangslink, der nulstiller brugerens adgangskode eller 2FA. Linket virker i 60 minutter. Sæt disse variabler i stack'en (Dockhand → Environment):

| Variabel | Eksempel | Bemærkning |
|---|---|---|
| `PUBLIC_URL` | `https://teamudvikling.saem.dk` | Bruges i linket i mailen. Påkrævet. |
| `SMTP_HOST` | `smtp.dinudbyder.dk` | Påkrævet. |
| `SMTP_PORT` | `587` | 587 (starttls) eller 465 (ssl). |
| `SMTP_SECURITY` | `starttls` | `starttls`, `ssl` eller `none` (kun internt relay). |
| `SMTP_USER` / `SMTP_PASSWORD` | | Brug en app-adgangskode, ikke din personlige. |
| `SMTP_FROM` | `U11 Udvikling <u11@saem.dk>` | Afsender. Påkrævet. |

Uden disse variabler virker appen som før; knappen til e-mail vises ikke.

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
