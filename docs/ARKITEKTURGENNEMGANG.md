# Kritisk arkitekturgennemgang (2026-11-22, v0.30.0)

Gennemgangen ser på systemet som helhed: udrulning, data, hemmeligheder, drift og kodens struktur. Den supplerer de tre
sikkerhedsgennemgange af koden i [SECURITY.md](SECURITY.md). Prioritet: **Kritisk** = risiko for tab eller læk af børns data,
**Høj** = bør løses før bred brug, **Mellem** = bør planlægges, **Lav** = forbedring.

## Sammenfatning

Applikationslaget er stærkt for et system af denne størrelse: alt er låst som standard, der er obligatorisk 2FA, holdisolation
testes automatisk på alle ruter, CSP er streng, og containeren kører med minimale rettigheder. De største risici ligger nu i
**driften omkring appen**. Alle data, nøgler og backupper ligger på én disk i én NUC i et privat hjem, og der er ingen kopi andre
steder. To indstillinger kan desuden svække login-beskyttelsen, hvis de står forkert.

## Fund og forslag

| # | Fund | Prioritet | Status |
|---|---|---|---|
| A1 | Backupperne ligger på samme disk og i samme volumen som databasen | **Kritisk** | Forslag (driftstjek minder om det) |
| A2 | `secret_key` og `totp_key` ligger i samme volumen som databasen | **Høj** | Forslag + driftstjek; `TOTP_KEY` i compose |
| A3 | Porten bindes til `0.0.0.0` som standard; med `TRUSTED_PROXIES=1` kan en klient på LAN forfalske sin IP | **Høj** | Forslag |
| A4 | Forkert `COOKIE_SECURE`/`TRUSTED_PROXIES` bag Cloudflare giver ingen fejl, men svækker cookies og login-spærre | **Høj** | **Rettet**: driftstjek i Administration og i loggen |
| A5 | Engangslinks (nulstilling, invitation, spillerlink) stod i gunicorns adgangslog | **Høj** | **Rettet**: `gunicorn.conf.py` fjerner tokens; CI tjekker det |
| A6 | Backup blev kun taget, når nogen loggede ind | **Mellem** | **Rettet**: baggrundstråden tager daglig backup |
| A7 | Ingen kryptering af data i hvile (disken i NUC'en) | **Mellem** | Forslag |
| A8 | Administration og login kan nås fra hele internettet (kun beskyttet af appens egen login) | **Mellem** | Forslag |
| A9 | Ingen overvågning eller alarm (nede, fuld disk, fejlet backup, fejlende mails) | **Mellem** | Forslag |
| A10 | Store PNG/WebP-billeder (op til 40 MP) kan presse 512 MB-grænsen, hvis flere uploades samtidig | **Mellem** | Forslag |
| A11 | `compose.yaml` bruger `:latest` som standard; afhængigheder er versionsintervaller uden hashes | Lav–mellem | Forslag |
| A12 | Restore er ikke afprøvet mod en rigtig backup (B-004) | Mellem | Åben (din opgave) |
| A13 | `admin.py` (≈900 linjer) og `team.py` (≈500) samler mange ansvarsområder | Lav | Forslag |
| A14 | CSP tillader inline-styles (`style-src 'unsafe-inline'`) | Lav | Accepteret (se SECURITY.md) |
| A15 | Fast struktur 4 × 6 kriterier i beregningerne | Lav (funktionel) | B-042b |

### A1 · Backupperne ligger samme sted som databasen — Kritisk
**Risiko:** En diskfejl, ransomware, en fejlagtig `docker volume rm` eller tyveri af NUC'en fjerner både data og alle backupper.
**Forslag:**
1. Kopiér `/data/backups` krypteret til et andet sted hver nat, fx med **restic** eller **rclone crypt** til en ekstern disk, en NAS eller en cloud-bucket (Backblaze B2, Hetzner Storage Box). Se `docs/BACKUP.md`.
2. Behold mindst 7 daglige og 4 ugentlige kopier.
3. Sæt `BACKUP_OFFSITE=1`, når det kører; så forsvinder påmindelsen i Administration.
4. Afprøv en gendannelse (A12/B-004).

### A2 · Nøglerne ligger i datavolumen — Høj
**Risiko:** En kopi af volumen giver både databasen, nøglen til at forfalske sessioner (`secret_key`) og nøglen til at dekryptere alle 2FA-hemmeligheder (`totp_key`). Krypteringen af 2FA giver så ingen beskyttelse.
**Forslag:**
1. Sæt `SECRET_KEY` som miljøvariabel i Dockhand (en ny nøgle logger blot alle ud).
2. Kopiér **indholdet** af `/data/totp_key` til miljøvariablen `TOTP_KEY` (præcis samme nøgle, ellers virker ingen 2FA). Gem den i en password-manager, og slet filen bagefter.
3. Tag ikke miljøvariablerne med i backupperne.

### A3 · Porten er åben på LAN — Høj
**Risiko:** Med `TRUSTED_PROXIES=1` stoler appen på `X-Forwarded-For`. Kan en enhed på hjemmenettet nå port 1020 direkte, kan den angive en vilkårlig IP og omgå IP-spærren mod gætteri af adgangskoder. Porten er heller ikke beskyttet af Cloudflare.
**Forslag:** Lad kun cloudflared kunne nå appen. Enten `U11_BIND=127.0.0.1` (hvis cloudflared kører på værten eller med host-netværk), eller kør cloudflared i samme Docker-netværk som appen og fjern `ports:` helt. Tjek bagefter fra en anden maskine, at `http://<nuc-ip>:1020` ikke svarer.

### A4 · Farlige indstillinger giver ingen fejl — Høj → rettet
Driftstjekket (`app/selfcheck.py`) viser nu en rød boks i Administration og skriver i loggen ved start, hvis siden kører på https uden `COOKIE_SECURE=1` eller `TRUSTED_PROXIES`. Det minder også om nøglerne i volumen, manglende backup og off-site-kopi.

### A5 · Engangslinks i loggen — Høj → rettet
gunicorn skrev hele URL'en, fx `/nulstil/<token>`, i adgangsloggen, og den kan læses i Dockhand. Et nulstillingslink er gyldigt i en time. Nu erstatter `gunicorn.conf.py` tokens med `…` i sti, forespørgselslinje og Referer. CI-røgtesten kalder en token-URL og fejler, hvis den står i loggen.

### A6 · Backup kun ved login — Mellem → rettet
Den daglige backup blev kun udløst af et login. Baggrundstråden tjekker nu hver time og tager backup, hvis den seneste er over 24 timer gammel.

### A7 · Ingen kryptering i hvile — Mellem
**Risiko:** Stjæles NUC'en eller dens disk, kan databasen læses direkte. Det gælder børns navne, fødselsdatoer, billeder og vurderinger.
**Forslag:** Fuld diskkryptering på NUC'en (LUKS ved installation, eller et krypteret volumen til Docker-data) og krypterede off-site-backupper (A1). Kryptering inde i SQLite (SQLCipher) anbefales ikke; det gør driften mere skrøbelig for lille gevinst.

### A8 · Administration er åben mod internettet — Mellem
**Forslag (stigende beskyttelse):**
1. Cloudflare WAF-regel med rate-limit på `/login*`, `/invitation*`, `/svar*` og `/nulstil*` (står allerede på din liste).
2. **Cloudflare Access** (gratis til få brugere) foran `/admin*`: kræver engangskode på e-mail, før forespørgslen overhovedet når NUC'en.
3. Overvej Access foran hele siden, så kun inviterede e-mails kan se login-siden. `/svar/*` skal så undtages, fordi forældre bruger det uden konto.

### A9 · Ingen overvågning — Mellem
**Forslag:** Uptime Kuma (container på NUC'en) eller Cloudflare Health Checks mod `/healthz` med besked til telefonen. Tilføj senere et lille endpoint eller en mail, der advarer ved fejlet backup, mails der er opgivet, eller disk over 80 %.

### A10 · Hukommelse ved billedupload — Mellem
**Risiko:** En PNG/WebP på 40 MP fylder ca. 160 MB i hukommelsen, plus kopier ved konvertering. Fire samtidige uploads (2 workers × 2 tråde) kan ramme containerens 512 MB, så den genstarter. Det kræver login, men kan også ske ved et uheld.
**Forslag:** Sænk grænsen for PNG/WebP til 16 MP (JPEG skaleres allerede ned under afkodning og kan beholde den høje grænse). Alternativt `mem_limit: 768m`.

### A11 · Forsyningskæde — Lav–mellem
**Forslag:**
1. Sæt `U11_IMAGE=ghcr.io/mikaelkandreasen/u11-udvikling:X.Y.Z` (fast version) i Dockhand frem for `latest`, så en uventet udgivelse ikke rulles ud ved en genstart.
2. Lås afhængighederne med hashes (`pip-compile --generate-hashes` → `requirements.lock`, installér med `--require-hashes`).
3. Fastlås GitHub Actions til commit-SHA, og slå Dependabot til for pip, Docker og Actions.

### A12 · Gendannelse ikke afprøvet — Mellem
Backupperne valideres automatisk, men en fuld gendannelse er ikke prøvet. Følg `docs/BACKUP.md` og `scripts/restore.sh` mod en kopi, før holdet bruger appen for alvor.

### A13 · Store moduler — Lav
`admin.py` samler brugere, hold, klubber, runder, import/eksport, backup, opbevaring, logs og e-mail-kø. Det er ikke en sikkerhedsfejl, fordi hele blueprintet er beskyttet, men det øger risikoen for fejl ved ændringer. **Forslag:** Del op i `admin_users.py`, `admin_teams.py`, `admin_data.py` (import/eksport/backup/opbevaring) og `admin_ops.py` (logs, mail, driftstjek) med samme blueprint og beskyttelse. Det kan gøres sammen med B-041c (adgangslag).

## Anbefalet rækkefølge
1. **A1 + A12:** off-site-backup og en afprøvet gendannelse.
2. **A2 + A3:** nøgler som miljøvariabler og porten lukket for LAN.
3. **A8:** rate-limit-regler og Cloudflare Access for `/admin*`.
4. **A7, A9, A11:** diskkryptering, overvågning, fast image-version.
5. **A10 og A13** i en kommende kodeversion.

Efter skridt 1–3 viser Driftstjekket i Administration ingen fejl.
