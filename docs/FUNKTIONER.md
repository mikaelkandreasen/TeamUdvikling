# Funktionsbeskrivelse – Team Udvikling

Hvad systemet gør, for hvem og hvordan. Teknik og struktur: [ARCHITECTURE.md](ARCHITECTURE.md). Processer på tværs af roller: [SWIMLANES.md](SWIMLANES.md).

## 1. Formål

Team Udvikling hjælper trænere på børnehold med at følge hver spillers udvikling over en sæson. Udgangspunktet er DBU's model
med fire roller (boldholder, medspiller, presspiller, støttespiller) og seks nøglefærdigheder (teknik, bevægelse, scanning, timing,
positionering, maskering). Systemet erstatter et Excel-ark og gør det muligt for flere trænere at arbejde på samme data,
sikkert og afgrænset pr. klub og hold. Det er børnefodbold: tallene skal støtte udvikling og samtale, ikke rangere børn.

## 2. Brugere og roller

*Menuen tilpasses rollen (`app/nav.py`): administratorer ser administration, trænere holdets sider, assistenter uden kampe/holdsætning/motivation/udviklingsdata/rapporter, chef-trænere desuden «Mit hold» og «Assistenter» (invitation af trænere og assistenter). Assistenters begrænsning er også låst på serveren.*

| Rolle | Hvem | Kort |
|---|---|---|
| **Assistent** | Hjælpetræner | Kan se alt på sine hold og evaluere. Evalueringen tæller kun med, hvis chef-træneren vælger det. Kan ikke ændre andet. |
| **Træner** | Træner på et eller flere hold | Daglig brug: spillere, evaluering, fremmøde, kampe, motivation, rapporter, noter. |
| **Chef-træner** | Træner markeret som chef for holdet | Som træner + holdindstillinger, evalueringsrunder, funktionsvalg, kalenderlink, besked til holdet, invitationer til eget hold. |
| **Klubadministrator** | Klubbens kontaktperson | Klubprofil (navn, logo, farve, motto), brugere og hold i klubben, besked til hele klubben, opbevaringsfrist. |
| **Systemadministrator** | Den, der driver serveren | Alle klubber, sletning, eksport/import, backup, sikkerhedslog, e-mail-kø, driftstjek, besked til alle. |
| **Spiller/forælder** | Uden login | Udfylder kun motivationsskemaet via et personligt engangslink. |

En bruger kan have flere profiler (fx træner i én klub og klubadministrator i en anden) og skifte mellem dem og mellem sine hold i topbjælken.

## 3. Funktioner

### 3.1 Login og konto
- Planlagt automatisk backup (ugedage, klokkeslæt, antal) med `latest.db`/`latest.json` til eksterne hentejobs.
- Systemadministrator kan gendanne en backup via siden (kontrol, sikkerhedskopi af nuværende database, frisk 2FA-kode).
- Login med brugernavn, adgangskode (mindst 12 tegn) og **obligatorisk 2FA** (autentificeringsapp). Gendannelseskoder ved tabt telefon.
- «Husk denne enhed» i op til 30 dage (kan glemmes under Min konto).
- Min konto: skift adgangskode, glem enheder, nye gendannelseskoder, **sprogvalg** (dansk, engelsk, tysk, svensk, norsk).
- Automatisk log ud efter 45 minutters inaktivitet (maks. 8 timer).

### 3.2 Forside
- Hjem (pc) og mobilforside med store knapper: egen evalueringsstatus, holdets fokus, nye beskeder, genveje.
- «Aktive nu» viser hvem på holdet der er logget ind.

### 3.3 Spillere
- Opret og ret: navn, fødselsdato (→ fødselskvartal), trøjenummer, op til fire positioner, fod, startdato, fokusområder, noter, aktiv/inaktiv.
- Billede med samtykkedato (EXIF/GPS fjernes, beskæres til kvadrat).
- Flyt spiller til andet hold (evalueringer følger med som historik). Eksport af alle data (JSON) til indsigt.

### 3.4 Evaluering
- Op til 20 runder pr. hold (standard 4) med navn og dato. Hver træner scorer hver spiller 1–5 på 24 kriterier; tomme felter er tilladt.
- DBU-niveauudsagn (A–D) pr. kompetence og en samlet niveauvurdering (A+, A, B, C, D, Nystartet).
- En runde åbnes ved første indtastning og lukkes efter 30 dage; chef-træner/administrator kan genåbne.
- En runde vises først i oversigter, når alle aktive spillere er evalueret.
- Chef-træneren vælger pr. runde, om assistenternes evalueringer tæller med.
- Holdet kan skrive egne tekster til de 24 kriterier.

### 3.5 Oversigter og analyse
- **Teamoversigt**: rolle-gennemsnit og samlet score pr. spiller, enighed mellem trænere, farvekodet (standard: 1 rød, 2 gul, 3 grøn = årgangsniveau, 4 mørkegul, 5 lyseblå; holdet kan vælge egne farver).
- **Udvikling**: roller og færdigheder runde for runde, også pr. position.
- **Position & bane**: spillerne på en bane efter position og score.
- **Områder**: holdets stærkeste og svageste kriterier.
- **Spillerprofil**: radar, de to seneste komplette runder (flere kan foldes ud), styrker, udviklingspunkter, største fremgang, niveau, historik.

### 3.6 Holdside
- Indstillinger: kamptype (fx 5v5, 8v8), udskiftere, slogan, maskotnavn, kalenderlink, funktionsvalg.
- **Farver for score 1–5**: egen farve og forklaring pr. tal, glidende eller faste blokke; forklaringen vises nederst på sider med farvede scores.
- Spillerniveau, holdets fokus (fælles fokuspunkter), holdnoter (wiki-agtige, søgbare), maskot (hvem har den med hjem), kalender.
- Sæsonskifte: nyt hold ud fra det gamle (uden scores og noter); det gamle kan arkiveres som skrivebeskyttet.

### 3.7 Motivation og træningsønsker
- 22 spørgsmål i tre kategorier (holdet kan rette tekster). Svar 1–5.
- Udfyldes på tablet under træning eller via et personligt **spillerlink** (7 dage, engangs, viser kun fornavn).
- Matrix over holdet og rapport pr. spiller med udvikling over tid.

### 3.8 Udviklingsdata
- Relativ alder (fødselskvartal, overvægt af tidligt fødte).
- Fremmøde pr. træning/kamp (afkrydsning; kan oprettes fra kalenderen), kampdeltagelse.
- Trivsel over tid (tre udsagn), motorik (fire områder), handleplan (tiltag, eget mål, opfølgning, status).

### 3.9 Holdsætning
- Opstillinger pr. kamptype og formation; idealopstilling; positionsmatch ud fra spillernes positioner.
- Deling af truppen i op til ni hold (A/B/C) efter niveau.

### 3.10 Kampe og spilletid
- Opret kamp (dato, modstander, kamptype, opstilling, perioder × minutter) – eller **hent kampforslag** fra holdets kalender
  (dato, tid, sted og modstander udfyldes; samme kamp oprettes ikke to gange).
- Sæt spillere på pladser periode for periode; kopiér periode 1; bænken vises.
- **Opstillingsforslag**: fordeler spilletiden jævnt og giver først spillerne positioner, de aldrig har prøvet. Fravær og målmand vælges.
- **Spilletid og hvide pletter**: minutter pr. spiller og positionsgruppe over alle eller de seneste 3/5/10 kampe; markerer lav spilletid.

### 3.11 Rapporter og samtaler
- Spillerrapport (A4) og **forældrerapport** med klublogo, motto, holdslogan og maskotbillede; positiv formulering.
- Udskriv alle på én gang.
- Samtaler: dato, noter, aftaler og hjemmeøvelse pr. spiller.

### 3.12 Beskeder
- Indbakke med tæller i topbjælken. Chef-træner skriver til holdet, klubadministrator til klubben, systemadministrator til alle.
- Vises på forsiden ved næste login; kan markeres læst; privat svar til afsender; afsender ser hvor mange der har læst.
- Valgfrit også som e-mail (sendes i baggrunden med genforsøg).

### 3.13 Administration
- **Klubadministration** (klubadministrator): én side med klubbens nøgletal, opgaver der kræver opmærksomhed, klubbens hold og genveje til alt, rollen må rette – kun egen klub.
- Brugere (opret, roller, hold, stop, «se som» skrivebeskyttet), invitationer, hold (opret, arkivér, slet), klubber og klubprofil.
- Evalueringsrunder (navn, dato, genåbning, assistenter), indstillinger, import fra Excel/CSV (forhåndsvisning før import), eksport til Excel.
- Backup (download), opbevaringsfrist for inaktive spillere, sikkerhedslog (30 dage), revisionslog, brugsstatistik, e-mail-kø, **driftstjek**, intern backlog.

## 4. Data og privatliv
- Alle data ligger i én database på klubbens/trænerens egen server. Ingen tredjeparts-sporing eller -scripts.
- Hvert hold ser kun egne spillere; hver klub kun egne hold og brugere.
- Sletning af en spiller sletter alle tilhørende data. Inaktive spillere kan slettes automatisk efter en frist.
- Revisionsloggen gemmer handlinger, aldrig scores eller adgangskoder. Se [GDPR.md](GDPR.md) og [FORAELDREINFO.md](FORAELDREINFO.md).

## 5. Ikke-funktionelle krav
| Område | Krav |
|---|---|
| Mobil | Alt kan bruges på en 360–430 px telefon; trykflader ≥ 44–48 px; tabeller bliver til kort |
| Uden JavaScript | Alle funktioner virker; JS giver kun bekvemmelighed (autosubmit, opdatering uden sideskift) |
| Sprog | Dansk standard; en/de/sv/no delvist oversat (B-045) |
| Sikkerhed | 2FA, holdisolation, CSP, CSRF, krypterede 2FA-nøgler; se [SECURITY.md](SECURITY.md) |
| Drift | Én container; daglig backup; migrationer med backup før; driftstjek i Administration |
| Ydelse | Dimensioneret til en klub med få hundrede brugere og spillere |

## 6. Begrænsninger
- Strukturen er fast: 4 roller × 6 færdigheder (B-042b).
- Ingen tilmelding/afbud til træning (idé i backlog).
- Ændringer i kalenderen (flyttet/aflyst kamp) opdaterer ikke allerede oprettede kampe.
- Oversættelserne dækker endnu ikke alle sider.
