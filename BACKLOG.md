# Backlog

Prioriteret liste. Øverst = næste. Format: `ID · titel · størrelse (S/M/L) – accept (hvordan vi ved, den er færdig)`.
Opdatér ved hver ændring: flyt færdige punkter til "Færdigt" og tilføj nye opdagelser nederst i "Idéer".

## Næste (P0 – før første rigtige brug)
- **B-001 · Verificér Docker-build og Dockhand-deploy** · S – `docker compose up --build` starter; `/healthz` svarer; data overlever `docker compose down && up`; Dockhand-stack kører fra GHCR-image.
- **B-002 · HTTPS bag reverse proxy** · S – vejledning (Caddy/Traefik/Nginx Proxy Manager) i README; `COOKIE_SECURE=1` testet; HSTS-header valgfri via env.
- **B-003 · Første rigtige gennemløb med trænere** · M – 1 hold, 2 trænere, 1 evalueringsrunde, motivationsskema på tablet; liste over friktionspunkter → nye backlog-punkter.
- **B-004 · Backup-restore afprøvet** · S – `scripts/restore.sh` testet mod en rigtig backup; beskrivelse af off-site kopi (fx rsync/rclone af volumen).

## Senere (P1)
- **B-010 · Holdadministratorer** · M – rolle "hovedtræner" kan oprette/nulstille trænere og redigere indstillinger for *egne* hold uden at være systemadmin. Isolationstests.
- **B-011 · Skrivebeskyttet rolle** · S – "assistent/forælderhjælper" kan se, men ikke ændre.
- **B-012 · Sæsonskifte** · M – kopiér hold til ny sæson (spillere + trænere, uden scores), arkivér det gamle; arkiverede hold er skrivebeskyttede.
- **B-013 · Rediger kriterie-beskrivelser pr. hold i UI** · M – `model.DESC` bliver standard; hold kan overskrive tekster; ændringer logges.
- **B-014 · Trivsel og motivation over tid** · M – flere målinger (datoer) i stedet for én værdi; linjediagram i rapporten.
- **B-015 · Fremmøde pr. træning/kamp** · M – registrér dag for dag (mobilvenlig afkrydsning) i stedet for tællere; beregn fremmøde automatisk.
- **B-016 · Tokenbaseret spillerlink** · M – engangslink (udløber) så spilleren kan svare på sin egen telefon uden login; kun motivationsformularen; ingen andre data synlige.
- **B-017 · 2FA-hærdning** · S – krav om adgangskode ved gen-opsætning af 2FA; kryptér TOTP-hemmeligheder med nøgle fra miljøet.
- **B-018 · Rate limiting pr. IP** · S – udover kontolåsning; log + valgfri blokering.
- **B-019 · Serverside PDF** · M – rapport som PDF-download (fx WeasyPrint) uden browserens print-dialog.
- **B-020 · Opbevaringspolitik (GDPR)** · M – påmindelse/automatisk anonymisering af inaktive spillere efter N måneder; skabelon til forældreinformation.

## Idéer (uprioriteret)
- Import fra den gamle Excel-model (engangs-admin-værktøj; bevidst udeladt i v0.1.0, fordi første version skal starte uden spillerdata).
- Sammenligning af en spiller mod egen tidligere runde i rapporten (tekstlig "hvad har ændret sig").
- Forslag til træningsfokus pr. hold ud fra laveste områder og spillernes ønsker.
- PWA (installér på hjemmeskærm, offline-visning af spillerliste).
- Playwright-/UI-tests af mobil-flowet; tilgængelighedstjek (kontrast, skærmlæser).
- Eksport af rapport som billede til deling med forældre.
- Flere sprog (da/en) via oversættelsesfiler.

## Færdigt
- **v0.1.0** – Første version: flere hold med separate trænerlogins, login + obligatorisk TOTP-2FA (gendannelseskoder, lockout), 4 roller × 6 nøglefærdigheder × 4 runder × flere trænere, teamoversigt (enighed), udvikling, position & bane, områder, spillerprofil (radar), motivation (22 spørgsmål, tablet-visning), udviklingsdata (relativ alder, fremmøde, trivsel, motorik, handleplan), spillerrapport (A4), mobilforside + bundmenu, admin (hold, brugere, runder, backup, Excel-eksport, revisionslog), Docker + CI + versionsstyring. Ingen spillerdata medfølger.
