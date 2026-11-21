# Beslutningslog

Kort format: **Kontekst → Valg → Konsekvens.** Nyeste nederst.

## 001 – Flask + SQLite + server-renderet HTML
Kontekst: selvhostet på en lille hjemmeserver, få samtidige brugere, skal kunne vedligeholdes af én person.
Valg: Flask, stdlib `sqlite3`, Jinja, server-SVG, minimal JS. Konsekvens: få afhængigheder, nem backup (én fil), ingen build-trin.

## 002 – Egen TOTP-implementering
Kontekst: miljøet, hvor v0.1.0 blev bygget, havde ikke netværk til pakkeinstallation (`pyotp` kunne ikke testes).
Valg: ~40 linjer stdlib (RFC 6238, testet mod officielle testvektorer). Konsekvens: kan skiftes til `pyotp` senere uden dataændring.

## 003 – Hold som afgrænsning for al data
Kontekst: flere hold med egne trænere. Valg: `players.team_id` er roden; evalueringer/svar/udviklingsdata nås via spilleren; indstillinger og
spørgsmål er pr. hold. Konsekvens: nye forespørgsler skal afgrænses (se CLAUDE.md regel 1); sletning af hold cascader.

## 004 – Ingen Excel-import i v0.1.0
Kontekst: første version skal starte uden spillerdata. Valg: ingen importer; admin-eksport til Excel findes. Konsekvens: evt. import kommer som backlog-punkt.

## 005 – Spillerdata kun i databasen, aldrig i repoet
Valg: `.gitignore` udelukker `data/`, `*.db`, `.env`; tests bruger opdigtede navne.

## D-008 · Klubprofil som globale indstillinger (2026-11-17)
Gemt i `settings` med nøgler `club:*` (ikke pr. hold). Logo som fil i `/data/branding`, serveret offentligt fra `/branding/logo` (så login kan vise det). Kun PNG/JPEG/WebP efter indholdstjek; SVG afvist (script-risiko).

## D-009 · KampKlar afventer valg (2026-11-17)
Ingen officiel API. Muligheder: (1) iCal-feed for holdets aktiviteter, (2) uofficiel login-scraper bag feature-flag med krypterede legitimationsoplysninger, (3) manuel/CSV-import. Claude API bruges ikke til datahentning. Børnedata og DBU's vilkår skal vurderes før (2).

## D-010 · E-mailnulstilling kun efter admin-godkendelse (2026-11-19)
Kontekst: trænere skal kunne få nulstillet adgangskode/2FA uden at admin læser en midlertidig kode op. Valg: ingen offentlig «glemt adgangskode»; admin bekræfter med egen 2FA-kode og udløser en mail med engangslink. 2FA-linket kræver også brugerens adgangskode. Linket bygges af `PUBLIC_URL`, ikke Host-headeren. Konsekvens: færre angrebsflader; kræver SMTP-opsætning. De gamle «Nulstil»-knapper (midlertidig kode) beholdes som nødvej, når mail ikke er sat op.

## D-011 · Billeder som BLOB i databasen og fast positionsordforråd (2026-11-19)
**Kontekst:** Billeder af børn er personoplysninger; der skal være ét sted at backup'e, slette og hold-afgrænse.
**Valg:** Billeder gemmes genkodet (480 px + 96 px JPEG, uden metadata) som BLOB i SQLite, kun med registreret samtykke, leveres via hold-afgrænset endpoint. Positionerne er ét fast ordforråd (`model.POSITIONS`) som både dropdowns og opstillingspladser (`formations.py`) bruger, så forslag kan matche præcist (Højre/Venstre kant).
**Konsekvens:** Databasen og backups vokser (~30 KB pr. billede); sletning af spiller fjerner billedet; ingen filer uden for databasen.

## D-012 · Klubber, roller og invitationer (2026-11-21)
**Kontekst:** Flere klubber skal kunne bruge samme installation med eget udseende, egne hold og egne administratorer; nye trænere skal kunne oprette sig selv uden at administratoren kender deres adgangskode.
**Valg:** Tabel `clubs` (profil + logo som BLOB); `teams.club_id` og `users.club_id`; rollerne `admin` (system), `clubadmin`, `trainer`. Holdnavne unikke pr. klub (tabellen `teams` genopbygges ved migration). Invitation = engangslink (7 dage), sendt af administrator efter 2FA-bekræftelse; den inviterede vælger selv brugernavn/adgangskode og sætter 2FA op. Loginsiden bruger standardklubbens (ældste) udseende.
**Konsekvens:** Alle admin-visninger skal afgrænses til klubben; logoer er offentlige pr. klub-id (som før); backup rummer alle klubber.
