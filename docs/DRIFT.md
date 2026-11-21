# Drift: udgivelse, første gennemløb og ekstern scanning

## 1. Verificér CI og GHCR-image (B-030)
CI (`.github/workflows/ci.yml`) kører tests, en **røgtest af Docker-imaget** (startes ikke-root, `cap_drop ALL`, skrivebeskyttet rod; `/healthz` og `/setup` skal svare) og udgiver derefter imaget.
1. Push `main` og tags: `git push && git push --tags`.
2. GitHub → fanen **Actions** → kør `ci` for tagget. Alle jobs skal være grønne (`security` må give advarsler).
3. GitHub → din profil → **Packages** → `u11-udvikling`: der skal ligge tags `0.10.1`, `0.10`, `latest`. Første gang: *Package settings → Change visibility → Public* (eller giv Dockhand et token med `read:packages`).
4. Dockhand → stacken → **Redeploy** (hent nyeste image). Tjek versionsnummeret nederst på siden.
5. Fast version i stedet for `latest`: sæt `U11_IMAGE=ghcr.io/mikaelkandreasen/u11-udvikling:0.10.1` i stacken.
Rulle tilbage: sæt `U11_IMAGE` til forrige version og Redeploy (databasen opgraderes kun fremad – gendan først en backup fra før opgraderingen, se `docs/BACKUP.md`).

## 2. Første gennemløb med trænere (B-003)
Mål: ét hold, to trænere, én runde – og en liste over friktion.
- [ ] Systemadministrator opretter klub (navn, farve, logo) og hold; vælger chef-træner og holdindstillinger (kamptype, funktioner).
- [ ] Invitér to trænere på e-mail (tjek: mail ankommer, link virker, brugernavn-tjek, 2FA-opsætning på telefon, gendannelseskoder gemt).
- [ ] Opret/importer spillere (opdigtede data til prøven, ellers rigtige efter samtykke). Sæt niveau og positioner.
- [ ] Begge trænere evaluerer 3–4 spillere på **telefon** (360–430 px): tryk-flader, «Gem & næste», åbne rollepaneler.
- [ ] Teamoversigt: enighed mellem trænerne giver mening? Rapporten udskrives (A4) og læses af en træner uden forklaring.
- [ ] Motivationsskema på tablet med 1–2 børn (eller opdigtede svar).
- [ ] Holdsætning + «Del i A/B/C-hold».
- [ ] Log ud/ind på telefon med «husk mig»; tjek loginsiden (neutral) og at 2FA ikke driller.
- [ ] Hent backup og kør `scripts/verify-backup.py`.
Notér alt, der tog mere end ét forsøg eller krævede forklaring, som nyt punkt i `BACKLOG.md`.

## 3. Ekstern scanning af den rigtige adresse (B-022)
Scan kun dit eget system, og helst uden for træningstid. Cloudflare-reglen (`/login*`, `/nulstil*`, `/invitation*`, `/svar*`) vil blokere scanneren på `/login`, `/nulstil` og `/invitation` – det er meningen. Scanning uden login er nok som første trin.
```bash
# OWASP ZAP baseline (passiv; sikker at køre mod produktion)
docker run --rm -t -v "$PWD":/zap/wrk ghcr.io/zaproxy/zaproxy:stable \
  zap-baseline.py -t https://teamudvikling.saem.dk -r zap-rapport.html

# nuclei (kendte svagheder og fejlkonfigurationer)
docker run --rm projectdiscovery/nuclei -u https://teamudvikling.saem.dk -severity medium,high,critical

# Sikkerhedsheadere og TLS
curl -sI https://teamudvikling.saem.dk | grep -iE 'strict-transport|content-security|x-frame|referrer|permissions'
```
Forventet: HSTS, CSP uden `unsafe-inline` for scripts, ingen åbne mapper, alt bag login svarer med omdirigering. Gem rapporten uden for repoet, læs advarslerne, og opret et backlog-punkt for hver reel fund.
