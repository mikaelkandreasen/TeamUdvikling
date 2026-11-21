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

## D-013 · Holdindstillinger, chef-trænere og holddeling (2026-11-21)
**Kontekst:** Hold har forskellige behov (kamptype, hvilke data der spores), og en chef-træner skal selv kunne styre sit hold og invitere trænere uden klubadministrator.
**Valg:** Funktionsvalg som holdindstillinger (`feat_*`) med 404-guard pr. blueprint; chef-trænere i tabellen `team_heads` (flere pr. hold); de får adgang til holdindstillinger, evalueringsrunder og invitationer til egne hold, men ikke brugere, klubber eller eksport. Holddeling er en ren funktion (`split.py`): rang efter niveau (A+, A, B; uvurderede = C), derefter samlet score; A-holdene fyldes først, overskydende A-vurderede flyttes til B-holdene før B-spillere.
**Konsekvens:** Nye hold-sider skal afgrænses til `g.team` og have isolationstest; mascot-log og noter er personoplysninger (se GDPR).

## D-014 · Neutral loginside (2026-11-21)
**Kontekst:** En offentlig loginside med klubbens logo/navn afslører, hvilke klubber der findes, og vælger ikke klub for brugeren (brugernavne er globalt unikke).
**Valg:** Før login vises kun produktnavnet og standardfarver. Cookien `u11_lc` (klub-id, ingen hemmelighed) sættes kun ved «husk mig» og styrer udseendet på loginsiden for den enhed.
**Konsekvens:** Første gang på en ny enhed ses et neutralt login; udseendet kommer efter login.

## D-015 · Assistent som flag, spillerlink og arkiverede hold (2026-11-21)
**Kontekst:** Skrivebeskyttet adgang, svar uden login og sæsonskifte skulle bygges uden at duplikere rolle-logikken.
**Valg:** Assistent = træner med `users.readonly=1` (al hold-/klubafgrænsning genbruges; ændringer blokeres globalt). Spillerlink er et selvstændigt engangstoken (`player_links`) med eget offentligt endpoint og kun hash gemt. Arkiverede hold (`teams.archived`) er skrivebeskyttede for hold-sider, men kan læses og genåbnes.
**Konsekvens:** Nye skrive-endpoints i `players/evaluation/motivation/devdata/lineup/team` er automatisk låst på arkiverede hold; offentlige endpoints skal føjes til `PUBLIC` og beskyttes af tokens og `throttled`.

## D-016 · Afviste udvidelser og kendte rester (2026-11-21)
**Kontekst:** Server-PDF, login-side pr. klub, billedupload i bulk og PWA med offline-cache blev overvejet.
**Valg:** Ingen server-PDF (browserens «gem som PDF» dækker det; undgår tung afhængighed). Ingen login-side pr. klub (afslører klubber, jf. D-014). PWA kun som manifest, uden service worker, så ingen persondata caches på enheden. iCal-hentning er https-only med kontrol af offentlig IP; en rest-risiko (DNS-rebinding mellem kontrol og hentning) accepteres, fordi adressen kun kan sættes af chef-træner/administrator. Sikkerhedslog (`security_events`) gemmer IP og hændelsestype i 30 dage.
**Konsekvens:** Genovervej kun hvis der opstår et konkret behov.

## D-017 · Beregnet niveau (2026-11-21)
**Kontekst:** Niveau (A/B/C) var kun sat manuelt. Trænerne ønskede selv at vurdere spillerens samlede niveau, og at niveauet beregnes efter en fast fordeling.
**Valg:** Egen tabel `level_ratings` (ikke et 25. kriterie, så eksisterende beregninger og fremdriftstællere er uændrede). Fordeling 25/50/25 i `model.distribute_levels`; reserve er samlet score. Det beregnede niveau overskriver aldrig et fastsat niveau uden at en træner trykker på knappen.
**Konsekvens:** Fordelingen er relativ til holdet – en lille trup (under 4 spillere) giver få eller ingen A/C. Niveau vises som et oplæg til trænergruppen, ikke som rangering af børn.

## D-018 · Niveauer efter DBU (2026-11-21)
**Kontekst:** Niveau skal altid måles som DBU beskriver det (A, B, C, D), ikke med egne trin.
**Valg:** `model.LEVELS = A, B, C, D` og `LEVEL_INFO` med sammenfattede beskrivelser + kildelink; A+ og «Ny» udgår (migration til A og D). Beskrivelserne er omskrevet, ikke kopieret ordret (DBU Fyn ejer teksten); boksen linker til originalen. Beregnet niveau (D-017) giver kun A/B/C – D vælges manuelt.
**Konsekvens:** Ændrer DBU kriterierne, rettes teksten i `model.LEVEL_INFO`.
