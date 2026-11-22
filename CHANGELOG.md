# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/da/1.1.0/) · Versionering: [SemVer](https://semver.org/lang/da/).

## [Unreleased]

### Tilføjet
- **Klubmotto** (på Klubprofil-siden) ud over holdets slogan (på Holdindstillinger). Mottoet vises i rapporternes klubhoved, sloganet på forældrerapporten. Skema v18.

## [0.19.0] - 2026-11-22

### Tilføjet
- **Forældrerapport** (tal-fri): logo, slogan og maskotbillede, derefter «Det er … god til», «Her er … gået frem», «Det træner vi på nu» og hvad barnet er optaget af. Ingen scores, farver, niveauer eller sammenligning. Åbnes fra spillerprofilen og rapportlisten (👪).
- **Maskotbillede** pr. hold (Holdindstillinger), vises på forældrerapporten. Skema v17.

## [0.18.1] - 2026-11-22

### Ændret
- **Niveau ud fra samlet score:** uden niveauvurdering svarer samlet score 3 til B, 4 til A og 5 til A+ (2 = C, 1 = D).

## [0.18.0] - 2026-11-22

### Tilføjet
- **Evalueringer har navn og dato** (i stedet for «Evaluering 1»). Ny runde kræver begge dele. Hjem og Evaluering viser de 2 seneste og den næste; «Vis alle» åbner resten.
- **Runder lukker 30 dage efter første indtastning.** Lukkede runder kan ses men ikke rettes; en holdansvarlig kan genåbne (30 dage). Eksisterende runder lukker 30 dage efter opdateringen.
- **Stoppede trænere:** sletning af en træner med evalueringer fjerner loginet, men evalueringerne bevares som «Navn (stoppet)».
- **Spillere kan flyttes til et andet hold** (administrator). Evalueringer følger med som historik under «Tidligere hold» i profilen; øvrige data følger spilleren.
- Skema v16 (eval_history, users.stopped_at).

### Ændret
- **Spillerprofilen viser kun de 2 seneste færdige evalueringer** (alle aktive spillere evalueret); «Vis flere» åbner resten. Delvise og tomme runder skjules.
- **Scorefarver:** 1 rød, 2 gul, 3 grøn (målet), 4 mørkere gul, 5 lysere blå.
- Teamoversigt: holdets gennemsnit står øverst. Spillerliste på mobil-hjem er sammenklappet.

## [0.17.0] - 2026-11-22

### Ændret
- **Links uden adgang skjules:** «Del i A/B/C-hold» og «Spillerniveau» viser ikke længere et link til Holdindstillinger, hvis man ikke har adgang til dem som træner.
- **Hold-knappen er flyttet fra menuen til Hjem** (både mobil- og fuld version), sammen med en ny **Noter**-knap.
- **Noter er nu en delt wiki til holdets trænere:** hver note har titel, dato og tekst (op til 20.000 tegn), kan rettes af alle trænere på holdet (med «sidst rettet af»), kan søges, og kan slettes af forfatteren eller en holdansvarlig. Afgrænset til holdet. Skema v15 (migration tilføjer titel/dato, eksisterende noter beholdes).

## [0.16.0] - 2026-11-21

### Tilføjet
- **Niveauvurdering efter DBU's regneark «Niveaudeling»** (ud over de 24 kriterier): trænerne scorer ti kompetencer – Engagement, Interesse, Viden, Forståelse, Teknik, Boldkontrol, Spark, Hurtighed, Motorik og Fysik – som A, B, C eller D med DBU's beskrivelser (omskrevet tæt på arket) ved hvert valg. Er **alle ti A**, er spilleren **A+**; ellers bliver niveauet det, der er **flest af** (ved lighed det højeste). Gemmes pr. træner og runde; skema v14 (`dbu_checks`).
- Trænerens egen dropdown for samlet niveau vejer tungere end udledningen; uden dropdown bruges DBU-valgene, og de indgår i den automatiske 25/50/25-beregning (med antal/vægt af valg som tie-break).
- «?»-boksen viser nu også DBU's retningslinjer for holdsammensætning (A-, B-, C- og D-hold) og fleksibilitet efter stævner.

## [0.15.0] - 2026-11-21

## [0.14.0] - 2026-11-21

### Ændret
- **Niveauer: A+, A, B, C, D (nybegynder) og Nystartet** efter DBU's niveaudeling (A+ er appens egen gradering af de allerstærkeste). «Ny» hedder nu «Nystartet». Skema v13.
- **Trænerens samlede niveau er en dropdown** i evalueringen (i stedet for 1–5). Tidligere vurderinger omsættes (5→A, 4→B, 3→C, 2→D, 1→Nystartet).
- **Beregnet niveau sker automatisk** (ingen knap): vurderingerne fordeles efter score, som standard 25 % A / 50 % B / 25 % C. Andelen til A og C justeres pr. hold under Holdindstillinger (0–45 %). Et fastsat niveau på spilleren bruges frem for det beregnede.

### Tilføjet
- **Flere profiler pr. bruger:** en systemadministrator kan give en bruger ekstra profiler (træner, klubadministrator eller systemadministrator, med klub) under brugerens side. Brugeren vælger aktiv profil øverst; al adgang følger den aktive profil. Kun profilens ejer kan vælge den.
- **?-knap med forklaring** ved Samlet niveau i evalueringen, på Spillerniveau og på Del i hold: en boks over siden med DBU's beskrivelse af A-, B-, C- og D-niveau (samt blandet niveau og begynder) og link til kilden. Virker med mus (hover) og tryk/tastatur på mobil. Beskrivelserne er sammenfattet med egne ord.

## [0.13.0] - 2026-11-21

### Tilføjet
- **Samlet niveau pr. træner:** i evalueringen giver hver træner en samlet niveauvurdering (1–5) af spilleren, ud over de 24 kriterier. Vurderingen gemmes pr. træner og runde og kan rettes eller ryddes.
- **Beregnet niveau:** spillerne fordeles efter score – øverste 25 % = A, midterste 50 % = B, nederste 25 % = C. Score er gennemsnittet af trænernes niveauvurdering i seneste runde; uden vurdering bruges samlet score fra kriterierne. Ved lige score følger spilleren den bedre gruppe, og er alle ens, er alle B.
- Hold → Spillerniveau viser det beregnede niveau pr. spiller og har knappen «Brug beregnet niveau» (kun tomme felter, eller overskriv alle). Del i A/B/C-hold bruger det beregnede niveau, hvis spilleren ikke har et fastsat niveau.

### Ændret
- Skema v11: tabellen `level_ratings`. Indgår i spillerens dataudtræk og slettes sammen med runder/evalueringer.

## [0.12.1] - 2026-11-21

### Tilføjet
- **Sendte invitationer på Brugere-siden:** de seneste 15 med e-mail, rolle, status (afventer/brugt/udløbet/tilbagekaldt), afsender og tidspunkt. Klubadministratorer ser kun egen klub.

## [0.12.0] - 2026-11-21

### Tilføjet
- **Brugerstyring som oversigt:** Administration → Brugere er en kompakt liste (navn, rolle, klub, hold, «låst»/«ingen 2FA») med søgning og klubfilter. Nulstilling, e-mail, rolle, hold, assistent, oplåsning, «Se som træner» og sletning ligger på brugerens egen side (`/admin/users/<id>`), som også viser oprettet og senest logget ind.
- **Træningsfokus** (Hold → Træningsfokus): holdets svageste og stærkeste kriterier i seneste runde samt spillernes højeste scorer i motivationsskemaet.
- **«Siden sidste runde»** i spillerprofil og rapport: samlet udvikling og de største op- og nedture (≥ 0,5 point).
- **Print af opstilling** med spillerliste på A4.
- **PWA-manifest** (neutralt navn/ikon, ingen service worker og ingen cache af data) – appen kan lægges på hjemmeskærmen.
- Kriterietekster pr. hold, kalender via iCal, sikkerhedslog, opbevaringspolitik med automatisk sletning, testmail, valgfri tjek af lækkede adgangskoder (`PWNED_CHECK=1`), krav om frisk 2FA-kode ved nulstilling af 2FA/adgangskode.
- **TOTP-hemmeligheder krypteres** i databasen (Fernet). Nøglen ligger i `TOTP_KEY` eller `/data/totp_key` – **tag backup af nøglen separat**; mistes den, skal 2FA nulstilles.

### Rettet
- Opbevaringssiden kunne slette inaktive spillere på tværs af klubber; er nu afgrænset til egen klub.
- Tom `onclick` fjernet fra mascot-rapporten (CSP).

## [0.11.0] - 2026-11-21

### Tilføjet
- **Backup kontrolleres** (integritet, fremmednøgler, skemaversion) ved hver backup; ødelagte backups slettes i stedet for at fortrænge gode. `scripts/verify-backup.py`, `scripts/restore.sh` kontrollerer filen og gemmer den gamle database. Se `docs/BACKUP.md` (inkl. off-site med rclone/rsync).
- **CI røgtest** af Docker-imaget før udgivelse (ikke-root, `cap_drop ALL`, skrivebeskyttet rod). `docs/DRIFT.md`: verificering af GHCR/Dockhand, tjekliste til første gennemløb og kommandoer til ZAP/nuclei.
- **Sæsonskifte** (Hold → Sæsonskifte): nyt hold med aktive spillere (uden scores, fokus, noter og billeder), trænere og indstillinger; det gamle hold arkiveres som skrivebeskyttet (kan genåbnes under Administration → Hold).
- **Fremmøde pr. træning/kamp:** afkrydsning på mobil; fremmøde og kampdeltagelse i Udviklingsdata beregnes automatisk.
- **Trivsel over tid:** målinger med dato; seneste måling bruges i Udviklingsdata, og spillerrapporten viser et linjediagram mod holdets gennemsnit.
- **Assistent (læseadgang):** en træner kan markeres som assistent – kan se, men ikke ændre. Kan oprettes direkte eller via invitation.
- **Spillerlink:** personligt engangslink (7 dage) til motivationsskemaet uden login; kun dette ene skema, én gang, med QR-kode. Tilføj `/svar` til Cloudflare-reglen.

### Ændret
- Skema v10 (idempotent migration): `teams.archived`, `users.readonly`, `invitations.as_readonly`, `att_events`, `att_marks`, `wellbeing`, `player_links`.

### Dokumentation
- BACKLOG opdateret: færdige punkter flyttet, dublerede ID’er omnummereret (B-021–B-024), nye B-030/B-031.

## [0.10.1] - 2026-11-21

### Ændret
- **Neutral loginside:** logo, farver og klubnavn vises ikke længere før login. Kun hvis enheden husker seneste login («husk mig»), vises den klubs udseende, man sidst loggede ind i (en lille cookie med klub-id, samme levetid som «husk mig»; fjernes ved et login uden «husk mig»).

## [0.10.0] - 2026-11-21

### Tilføjet
- **Holdindstillinger** (chef-træner, klubadministrator, systemadministrator): kamptype (3/5/8/11 på banen) + antal udskiftere, slogan, mascot-navn og valg af hvilke funktioner holdet bruger (udviklingsdata, motivation, holdsætning, niveau, noter, mascot). Slåede-fra funktioner skjules og svarer 404; data bevares.
- **Chef-træner** pr. hold (flere mulige): må ændre holdindstillinger, oprette/fjerne evalueringsrunder (nu op til 20) og invitere trænere til eget hold. Vælges af klubadministrator under Hold – eller via invitation.
- **Invitation til chef-træner:** klubadministrator og chef-træner kan invitere en træner eller en chef-træner (chef-trænere kun til egne hold; kun klubadministrator kan invitere via alle klubbens hold).
- **Spillerniveau** A+, A, B, C, Ny – i spillerformularen og på en samlet side.
- **Del truppen i op til 9 hold** (3 × A, 3 × B, 3 × C; 1–3 pr. niveau) efter holdprofilen: A-holdene får A+/A og B, B-holdene B, C-holdene resten; mangler der spillere, fyldes A-holdene først. De bedste efter samlet score spiller; advarsel hvis et hold ikke kan stilles. Kan gemmes som opstillinger.
- **Holdnoter**, **slogan** (vises på forsiden) og **mascot med log og rapport** (hvem, hvor mange gange, hvorfor, hvem der ikke har haft den; periodefilter; udskrivning).
- **Brugernavn-tjek:** ved oprettelse via invitation vises live, om brugernavnet er ledigt (kontrolleres også ved oprettelse).
- **Systemadministrator: Alle brugere** – klub, hold, oprettet (dato/tid), senest logget ind og senest aktiv.

### Ændret
- Skema v9 (idempotent migration): `players.level`, `teams.slogan/mascot_name`, `team_heads`, `team_notes`, `mascot_log`, `invitations.as_head`, `users.last_login`. Maks. evalueringsrunder 8 → 20.

## [0.9.0] - 2026-11-21

### Tilføjet
- **Invitation på e-mail:** en administrator kan sende en invitation til en ny træner (eller klubadministrator). Personen åbner linket, vælger selv brugernavn og adgangskode og sætter 2FA op. Linket virker i **7 dage**, kan kun bruges én gang og kan tilbagekaldes eller sendes igen. Afsendelse kræver administratorens egen 2FA-kode (som ved nulstilling). Kun administratorer kan invitere.
- **Flere klubber:** hver klub har eget navn, egen farve og eget logo, egne hold og egne trænere. Klubbens udseende vises, når man er logget ind på et af klubbens hold. Holdnavne er unikke pr. klub.
- **Roller:** *Systemadministrator* (alt, opretter klubber og klubadministratorer), *Klubadministrator* (styrer egen klub: profil, hold, trænere, invitationer) og *Træner*. Alt fra andre klubber svarer 404.

### Ændret
- Skema v8: tabellerne `clubs` og `invitations`, `users.club_id`, `teams.club_id`. Eksisterende klubprofil og logo flyttes automatisk til klub 1, og eksisterende hold/trænere tilknyttes den. Rollen `admin` er nu systemadministrator.
- Logoer gemmes i databasen (indgår i backup) og hentes på `/branding/logo/<klub-id>`.

## [0.8.1] - 2026-11-19

## [0.8.0] - 2026-11-19

### Tilføjet
- **Aktive nu:** lille «(2 aktive)» ved navnet øverst til højre (administrator: «2/5 aktive» = eget hold/i alt). Tryk åbner en side med navne og tidspunkter. Trænere ser kun eget hold, aldrig navne fra andre hold.
- **Administration → Brug:** aktive brugere pr. 15 minutter over døgnet, ugedag × tidspunkt (varmekort), travleste tidspunkter og sidst aktiv pr. bruger. Filter på periode og hold. Lokal tid (`TZ`, standard Europe/Copenhagen).
- **Evaluering:** ved «Gem & næste» (og «‹ Forrige») forbliver de samme spillertyper (Boldholder, Medspiller, Presspiller, Støttespiller) åbne, og de andre er foldet sammen hos næste spiller.

### Privatliv
- Brugsstatistikken gemmer kun bruger, kvarter og hold – ingen sider, indhold, scores eller IP-adresser. Slettes efter 180 dage. Skema v7 (`presence`, `activity`).

## [0.7.1] - 2026-11-19

## [0.7.0] - 2026-11-19

### Tilføjet
- **Op til 4 positioner pr. spiller** med dropdowns (grupperet: Målmand, Forsvar, Midtbane, Kant, Angreb, Andet). Nye positioner: **Højre kant / Venstre kant**, Højre/Venstre back, Midtstopper, Defensiv/Offensiv midtbane. Position & bane viser Valg 1–4. Import/eksport har kolonnerne Position 3 og 4.
- **Holdsætning** (menu): opstillinger for 3v3, 5v5, 8v8 og 11v11 med flere spillesystemer pr. kamptype (fx 3-3-1, 2-3-2, 4-3-3, 4-4-2). Dropdown pr. plads, bænk, flere gemte opstillinger, ét **idealhold** pr. kamptype, og «Foreslå hold» ud fra spillernes positioner (valgfrit også ud fra scores). Forslag gemmes først ved «Gem».
- **Spillerbilleder** (kræver markeret forældresamtykke): beskæres kvadratisk, genkodes til JPEG, metadata/GPS fjernes. Vises som mini på Position & bane, Holdsætning, spillerlisten, profil og rapport. Slettes sammen med spilleren; indgår i backup og JSON-eksport.

### Ændret
- **Systemet hedder nu «Team Udvikling»** (før «U11 Udvikling») overalt: header, fanetitel, fodlinje, 2FA-appen og e-mails. Navnet kan ændres under Administration → Klubprofil → «Systemets navn».
- Skema v6 (`players.position3/4`, `player_photos`, `lineups`, `lineup_slots`; idempotent). Ny afhængighed: Pillow.

## [0.6.1] - 2026-11-19

### Sikkerhed
- Simuleret angreb på login bag Cloudflare (`tests/test_login_attack.py`, 25 angreb). Rettet: lås-DoS (kontolåsning er nu pr. bruger+IP, global grænse 25 fejl), brugeropremsning via svartid på låste konti, session-cookie der virkede efter log ud, samtidig genbrug af 2FA-kode, indeksering og versionsvisning på login-siden, grænse for inputlængde, advarsel ved `COOKIE_SECURE` uden `TRUSTED_PROXIES`. Se docs/SECURITY.md (inkl. Cloudflare-indstillinger).
- Skema v5 (`login_fails`, `revoked_sessions`; idempotent). Eksisterende sessioner logges ud én gang ved opdatering (husk-enheder virker stadig).

## [0.6.0] - 2026-11-19

### Tilføjet
- **E-mailadresse på brugere** (Administration → Brugere; vises skrivebeskyttet under Min konto).
- **Nulstilling af adgangskode eller 2FA via e-mail, efter administrators godkendelse med egen 2FA-kode.** Engangslink (60 min., maks. 3 pr. time). 2FA-nulstilling kræver også brugerens adgangskode, så e-mail alene aldrig omgår 2FA. Opsættes med `PUBLIC_URL` og `SMTP_*` (se README); uden dem er funktionen skjult.

### Ændret
- Skema v4 (`users.email`, `reset_tokens`; idempotent migration, ingen data slettes).

## [0.5.0] - 2026-11-18

### Tilføjet
- **Husk denne enhed i 30 dage** (flueben ved 2FA-login): logger ind uden adgangskode/2FA på den enhed. Fast udløb, roterende token med tyveridetektion, tilbagekaldes ved log ud/adgangskodeskift/2FA-nulstilling/«Glem alle enheder» (Min konto). Administration kræver stadig frisk login med kode. `REMEMBER_DAYS` (0 = fra).

## [0.4.0] - 2026-11-18

### Tilføjet
- **Backlog i Administration** med prioritet (P0–Idé), status, flyt op/ned og redigering; startliste følger med.
- **Evalueringsrunder pr. hold** (2–8, standard 4): tilføj runde, fjern sidste runde (sletter dens evalueringer) og slet scores pr. runde/træner/spiller (Administration → Evalueringer).
- **Se siden som træner**: administrator kan se præcis, hvad en bestemt træner ser (skrivebeskyttet, kun trænerens hold). Afsluttes med knap i banneret.
- Tydeligere valg af flere hold til en træner (funktionen fandtes allerede og er nu dækket af tests).

## [0.3.0] - 2026-11-18

### Tilføjet
- **Import af spillere og hold** (Administration → Import) fra Excel (.xlsx) eller CSV: skabelon, validering, forhåndsvisning før noget gemmes, nye hold oprettes, eksisterende spillere (hold + navn + fødselsdato) opdateres. Formler køres aldrig, filer gemmes ikke, revisionsloggen får kun antal.

## [0.2.3] - 2026-11-18

### Rettet
- Dockhand kan ikke bygge fra Git (skrivebeskyttet filsystem). `compose.yaml` henter nu det færdige image fra GHCR; `compose.build.yaml` bruges til lokal bygning. CI udgiver `latest` ved push til `main`, og sikkerhedsjobbet blokerer ikke længere udgivelsen.

## [0.2.2] - 2026-11-18

### Ændret
- `docker-compose.yml` hedder nu `compose.yaml` (Dockhands standardsti): en Git-stack kan oprettes uden yderligere indstillinger.

## [0.2.1] - 2026-11-17

### Sikkerhed
- **Kritisk:** første opsætning kræver nu altid en engangskode (genereres automatisk, vises i log/`/data/setup_token`, slettes efter brug).
- Login-spærre pr. IP (429), `TRUSTED_PROXIES` til korrekt klient-IP bag reverse proxy.
- Sessioner bindes til adgangskoden (stjålne cookies dør ved skift); nulstilling af 2FA afbryder aktive sessioner.
- Excel-eksport neutraliserer formler; gendannelseskoder 48 bit med nøglet hash; strengere `next`-validering.
- HSTS, Permissions-Policy, COOP/CORP, `__Host-`-cookie ved HTTPS; `/healthz` viser ikke version.
- Compose: `pids_limit`, `mem_limit`, valgfri `U11_BIND`; gunicorn-grænser; fastlåste afhængigheder; Dependabot, `pip-audit` og `bandit` i CI.
- Pentest som regressionstests (`tests/test_security.py`) og `docs/SECURITY.md`.

### GDPR
- Offentlig side `/privatliv`, admin-side *Dataoprydning* (slet inaktive spillere), audit-log slettes efter 12 mdr., `docs/GDPR.md` (dataregister, rettigheder, DPIA, brud).

## [0.2.0] - 2026-11-17

### Tilføjet
- Klubprofil (admin): klubnavn, kontaktinfo, fodtekst, primær farve (kontrastkontrol) og logo (indholdstjek, SVG afvist). Vises i header, login og rapporter.

### Ændret
- Standardport er nu **1020**; `docker-compose.yml` bygger direkte fra Git i Dockhand (image valgfrit via `U11_IMAGE`).

## [0.1.0] - 2026-11-17

### Tilføjet
- Flere hold med separate trænerlogins; trænere ser kun de hold, de er tildelt; administratorer ser alle. Holdskifter i headeren.
- Login med adgangskode + obligatorisk TOTP-2FA (RFC 6238), gendannelseskoder, kontolåsning, replay-beskyttelse, tvungent skift af midlertidig adgangskode, CSRF, CSP og sikkerhedsheadere.
- Evaluering: 4 runder × flere trænere × 24 kriterier (DBU's 4 roller × 6 nøglefærdigheder), scoreformular optimeret til mobil.
- Teamoversigt med rolle-gennemsnit, samlet score, enighed mellem trænere og fortolkning.
- Udvikling pr. runde, position & bane (primær/sekundær), områdeudvikling, spillerprofil med radardiagram, styrker og udviklingsområder.
- Motivation og træningsønsker: 3 kategorier / 22 pladser (blanke kan tages i brug), matrix-input, spillervisning til tablet/telefon, rapport.
- Udviklingsdata: relativ alder (kvartal), fremmøde, kampdeltagelse, trivsel, motorik og handleplan; holdoverblik for relativ alder.
- Spillerrapport (A4-print) pr. spiller og for alle spillere.
- Mobilforside (`/m`), bundmenu og responsive tabeller; auto-redirect til mobilforsiden på telefoner.
- Administration: hold, brugere, runder, automatisk daglig backup, hentning af backup, Excel-eksport, revisionslog, GDPR-indsigt (JSON) og sletning pr. spiller.
- Docker-image, `docker-compose.yml`, GitHub Actions (tests + udgivelse af image), `scripts/release.sh`, `scripts/restore.sh`.
- Dokumentation: `README.md`, `CLAUDE.md`, `BACKLOG.md`, `docs/ARCHITECTURE.md`.

### Bevidst udeladt
- Ingen spillerdata fra den gamle Excel-model; databasen starter tom.
