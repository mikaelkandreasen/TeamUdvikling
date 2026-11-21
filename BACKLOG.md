# Backlog

Prioriteret liste. Øverst = næste. Format: `ID · titel · størrelse (S/M/L) – accept (hvordan vi ved, den er færdig)`.
Opdatér ved hver ændring: flyt færdige punkter til "Færdigt" og tilføj nye opdagelser nederst i "Idéer".

## Næste (P0 – før første rigtige brug)
- **B-003 · Første rigtige gennemløb med trænere** · M – 1 hold, 2 trænere, 1 evalueringsrunde, motivationsskema på tablet; liste over friktionspunkter → nye backlog-punkter. *Status: Tjekliste i docs/DRIFT.md – selve gennemløbet udføres af dig.*
- **B-004 · Backup-restore afprøvet** · S – `scripts/restore.sh` testet mod en rigtig backup; beskrivelse af off-site kopi (fx rsync/rclone af volumen). *Status: Backup kontrolleres automatisk; scripts/restore.sh + verify-backup.py; docs/BACKUP.md (off-site med rclone/rsync).*

## Senere (P1)
- **B-011 · Skrivebeskyttet rolle** · S – "assistent/forælderhjælper" kan se, men ikke ændre.
- **B-012 · Sæsonskifte** · M – kopiér hold til ny sæson (spillere + trænere, uden scores), arkivér det gamle; arkiverede hold er skrivebeskyttede.
- **B-014 · Trivsel og motivation over tid** · M – flere målinger (datoer) i stedet for én værdi; linjediagram i rapporten.
- **B-015 · Fremmøde pr. træning/kamp** · M – registrér dag for dag (mobilvenlig afkrydsning) i stedet for tællere; beregn fremmøde automatisk.
- **B-016 · Tokenbaseret spillerlink** · M – engangslink (udløber) så spilleren kan svare på sin egen telefon uden login; kun motivationsformularen; ingen andre data synlige.
- **B-018 · Rate limiting pr. IP** · S – *delvist løst:* app-lås pr. konto/IP findes, og Cloudflare-regel dækker `/login`, `/nulstil`, `/invitation`. Mangler: blokeringslog i admin (valgfri).

- **B-021 · DBU KampKlar-integration** · M/L – Ingen officiel API. Undersøgt: uofficiel scraping af mit.dbu.dk (personligt DBU-login, kan gå i stykker, vilkår uafklarede) eller iCal-link til holdets kampe/aktiviteter. Uklart om andre spilleres tilmeldingsstatus er synlig. Claude API er ikke nødvendigt til hentning. Afventer brugerens valg – se docs/DECISIONS.md.

- **B-022 · Ekstern pentest/scan af udrullet system** · S – OWASP ZAP/nuclei mod HTTPS-adressen, før den åbnes på internettet. *Status: Kommandoer til ZAP/nuclei i docs/DRIFT.md – selve scanningen udføres af dig.*

> Bemærk: Administration → Backlog i appen er en separat, redigerbar liste i databasen. Denne fil er udviklerens reference; hold dem i takt ved større ændringer.

- **B-030 · Verificér CI/GHCR-udgivelse af Docker-image ved tag** · S – push af `vX.Y.Z` bygger og udgiver image til GHCR; Dockhand kan trække det. *Status: CI har røgtest af Docker-imaget før udgivelse; docs/DRIFT.md beskriver verificering af GHCR/Dockhand. Resterer: din første kørsel af workflowet.*

## Idéer (uprioriteret)
- Udskrivning af holdsætning (A4) til kampdag; deling som billede.
- Spillerbilleder: bulk-upload og automatisk sletning når samtykke trækkes tilbage.
- Ekstern scanning (ZAP/nuclei) af den rigtige adresse bag Cloudflare, når siden er oplagt (supplerer den lokale simulation).
- Tjek af adgangskoder mod lækkede lister (k-anonymitet) ved oprettelse/skift.
- Testmail-knap i Administration, så SMTP-opsætningen kan afprøves uden at nulstille en bruger.
- Mulighed for at kræve admin-2FA-kode også til de direkte «Nulstil»-knapper (midlertidig kode).
- ~~Import fra den gamle Excel-model~~ – der findes nu et admin-importværktøj (Administration → Import); selve spillerdata lægges stadig aldrig i repoet.
- Sammenligning af en spiller mod egen tidligere runde i rapporten (tekstlig "hvad har ændret sig").
- Forslag til træningsfokus pr. hold ud fra laveste områder og spillernes ønsker.
- PWA (installér på hjemmeskærm, offline-visning af spillerliste).
- Playwright-/UI-tests af mobil-flowet; tilgængelighedstjek (kontrast, skærmlæser).
- Eksport af rapport som billede til deling med forældre.
- Flere sprog (da/en) via oversættelsesfiler.

## Færdigt
- **v0.12.0** – B-013 kriterietekster pr. hold, B-017 2FA-hærdning, B-023 kryptering af TOTP-hemmeligheder, B-020/B-024 opbevaringspolitik og automatisk sletning, B-018 sikkerhedslog, kalender via iCal (kamptider uden DBU-scraping), testmail, valgfri tjek af lækkede adgangskoder, 2FA-kode til nulstillinger, brugeroversigt med detaljeside, træningsfokus, «siden sidste runde», print af opstilling, PWA-manifest. Afvist: B-019 server-PDF (browserens «gem som PDF» dækker behovet, jf. D-016), B-031 login pr. klub (strider mod neutral loginside, D-014).
- **v0.11.0** – B-004 backup/restore (kontrol + vejledning), B-030 CI-røgtest, B-003/B-022 tjeklister (docs/DRIFT.md), B-012 sæsonskifte, B-015 fremmøde pr. træning/kamp, B-014 trivsel over tid (motivation over tid mangler), B-011 assistent med læseadgang, B-016 spillerlink.
- **B-001** – Docker-build og Dockhand-deploy kører i drift på hjemmeserveren (CI/GHCR-udgivelse er stadig uverificeret – se B-030).
- **B-002** – HTTPS via Cloudflare Tunnel (`COOKIE_SECURE=1`, `__Host-`-cookies, ProxyFix).
- **B-010** – Holdadministratorer: klubadministrator og chef-træner (v0.9.0/v0.10.0), med isolationstests.
- **v0.10.0** – Holdindstillinger og funktionsvalg, chef-trænere (+ invitation), spillerniveau, holdnoter, slogan/mascot med rapport, deling i op til 9 A/B/C-hold, brugernavn-tjek, sysadmin-brugeroversigt, op til 20 evalueringsrunder.
- **v0.1.0** – Første version: flere hold med separate trænerlogins, login + obligatorisk TOTP-2FA (gendannelseskoder, lockout), 4 roller × 6 nøglefærdigheder × 4 runder × flere trænere, teamoversigt (enighed), udvikling, position & bane, områder, spillerprofil (radar), motivation (22 spørgsmål, tablet-visning), udviklingsdata (relativ alder, fremmøde, trivsel, motorik, handleplan), spillerrapport (A4), mobilforside + bundmenu, admin (hold, brugere, runder, backup, Excel-eksport, revisionslog), Docker + CI + versionsstyring. Ingen spillerdata medfølger.
