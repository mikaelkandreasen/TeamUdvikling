# GDPR-gennemgang (skabelon – skal godkendes af klubbens bestyrelse/DPO)

*Dette er en teknisk gennemgang og ikke juridisk rådgivning.*

## 1. Dataansvar og roller
- **Dataansvarlig:** klubben (ikke den enkelte træner). Træneren er medarbejder/frivillig under klubbens instruks.
- **Databehandler:** ingen, så længe systemet driftes på klubbens/trænerens egen server. Hvis det hostes hos en leverandør, skal der laves databehandleraftale.
- Registrerede: børn (U11, under 13 år), trænere, forældre (kun indirekte).

## 2. Oversigt over behandling (art. 30)
| Kategori | Eksempler | Formål | Kilde | Modtagere | Sletning |
|---|---|---|---|---|---|
| Barnets stamdata | navn, fødselsdato, position, trøjenr., fod | Tilrettelægge træning | Træner/forælder | Holdets trænere, admin | Når barnet stopper |
| Evalueringer | scores pr. nøglefærdighed | Udviklingsarbejde | Trænere | Holdets trænere, admin | Når barnet stopper |
| Motivation og ønsker | barnets svar | Tilpasse træning | Barnet | Holdets trænere, admin | Når barnet stopper |
| Udvikling og trivsel | fremmøde, trivsel, motorik, mål, tiltag, noter | Støtte barnet | Trænere/barnet | Holdets trænere, admin | Når barnet stopper |
| Trænerkonti | navn, brugernavn, e-mailadresse (valgfri), adgangskode-hash, 2FA-hemmelighed | Adgangskontrol og nulstilling efter admins godkendelse | Trænere/admin | Admin; e-mailudbyder (SMTP) ved afsendelse af nulstillingsmail | Når trænere stopper |
| Spillerniveau, noter og mascot | niveau (A+–Ny), holdnoter, hvem der har haft mascotten og hvorfor | Tilrettelægge hold og fællesskab | Trænere | Holdets trænere, admin | Når barnet stopper (mascot-log følger spilleren) |
| Fremmøde og trivsel over tid | dato for træning/kamp, hvem der var til stede; trivselsmålinger (1–5) | Støtte barnet, planlægge træning | Trænere/barnet | Holdets trænere, admin | Når barnet stopper |
| Spillerlink | hash af engangslink, svar på motivationsskema | Lade barnet svare hjemme | Barnet/forælder | Holdets trænere | Link: 7 dage; svar: når barnet stopper |
| Nulstillingstokens | hash af engangslink | Sikker nulstilling | System | Ingen | 60 min. (ryddes efter 1 døgn) |
| Logs | audit-log, loginforsøg | Sikkerhed/ansvarlighed | System | Admin | 12 mdr. / 1 time |

## 3. Retsgrundlag
Anbefalet: **samtykke fra forældremyndighedsindehaver** (art. 6(1)(a), art. 8) indhentet pr. barn, særskilt og kunne trækkes tilbage. Alternativ (legitim interesse, art. 6(1)(f)) er mere skrøbeligt, fordi det drejer sig om børns oplysninger, trivsel og vurderinger. Klubben skal vælge og dokumentere. Trivsel/motorik kan i visse tilfælde nærme sig helbredsoplysninger (art. 9) – hold dem **faktuelle og neutrale**, undgå diagnoser og følsomme beskrivelser i fritekstfelter.

### Import
Admin kan importere spillere fra Excel/CSV. Uploadede filer gemmes ikke; kun et midlertidigt, rensat resultat (maks. 30 min, slettes ved bekræftelse) ligger i `/data/import`. Brugeren skal selv slette kildefilen lokalt. Revisionsloggen indeholder kun antal.

## 4. Principper
- **Flere klubber:** hver klub er selvstændig dataansvarlig for sine hold; systemadministratoren (driften) har teknisk adgang til alle data. Klubadministratorer og trænere ser kun egen klub. Invitations-e-mails gemmes (adresse, tidspunkt) og kan tilbagekaldes.
- **Brugsstatistik for trænere:** systemet registrerer kun, at en træner var aktiv i et 15-minutters tidsrum (og på hvilket hold) samt sidste aktivitet; ingen sider, indhold eller IP-adresser. Slettes efter 180 dage. Bruges til at se travle tidspunkter og hvem der er aktive.
- **Dataminimering:** ingen CPR-nr., ingen adresser, billeder af børn kun med forældresamtykke (afkrydsning ved upload, tidspunkt gemmes; billedet genkodes uden GPS/metadata, slettes med spilleren), ingen forældredata. Fritekstfelter (noter, tiltag) må ikke bruges til følsomme oplysninger.
- **Formålsbegrænsning:** ikke til udtagelse alene og ikke til videregivelse.
- **Opbevaring:** *Dataoprydning* (Admin) sletter inaktive spillere permanent; backups overskrives efter 14 dage; audit-log efter 12 mdr.
- **Sikkerhed (art. 32):** se `docs/SECURITY.md` (2FA, adgangskontrol pr. hold, kryptering i transit via HTTPS, audit-log, backup).

## 5. Registreredes rettigheder
| Ret | Sådan opfyldes den |
|---|---|
| Indsigt (art. 15) | Admin → spiller → *Eksportér JSON* |
| Berigtigelse (art. 16) | Rediger spiller/scores |
| Sletning (art. 17) | Admin → slet spiller (alle data + kaskade), eller *Dataoprydning* |
| Begrænsning/indsigelse (art. 18/21) | Sæt spiller inaktiv; slet ved krav |
| Dataportabilitet (art. 20) | JSON-eksport pr. spiller; Excel-eksport pr. hold |
| Information (art. 13) | Offentlig side `/privatliv` (tilpas teksten) |

## 6. DPIA (art. 35)
Systematisk vurdering af børn kan udløse krav om konsekvensanalyse. Anbefaling: lav en kort DPIA før brug med rigtige data (formål, nødvendighed, risici, tiltag). Risici og tiltag følger af dette dokument og `docs/SECURITY.md`.

## 7. Brud (art. 33/34)
Ved mistanke om uautoriseret adgang: tag systemet offline, skift `SECRET_KEY` (logger alle ud), nulstil adgangskoder og 2FA, gennemse audit-log (Admin → Revisionslog), og anmeld brud til Datatilsynet inden 72 timer, hvis det udgør en risiko for børnene.

## 8. Åbne punkter for klubben
1. Vælg og dokumentér retsgrundlag; udarbejd samtykkeformular til forældre.
2. Tilpas `/privatliv` (kontaktoplysninger sættes under Klubprofil).
3. Aftal opbevaringstid for udtrådte spillere (anbefalet: slet senest 3 måneder efter udtræden).
4. Lav DPIA og dokumentér, hvem der har administratoradgang.
5. Tag stilling til, om DBU KampKlar-integration (B-010) må behandle børnedata hos tredjepart, før den bygges.

## Tilføjet i v0.12.0
- **Sikkerhedslog:** hændelsestype, brugernavn og IP gemmes i 30 dage og slettes automatisk.
- **Opbevaringstid:** inaktive spillere kan slettes efter aftalt frist (standard 12 mdr.), manuelt eller automatisk; kun i egen klub.
- **Spillerlink, fremmøde, trivsel, mascot-log og noter** er personoplysninger om børn og følger samme sletning som spilleren.
- **Niveauvurderinger** (trænernes samlede vurdering pr. spiller og runde) følger samme sletning som evalueringer og indgår i indsigtsudtrækket.
- **DBU-niveauvalg** (trænerens A–D pr. kompetence, pr. spiller og runde) følger samme sletning som evalueringer og indgår i indsigtsudtrækket.

- **Stoppede trænere og holdskifte:** en stoppet træners login, e-mail og 2FA fjernes; kun navn + «(stoppet)» og evalueringerne bevares som historik. Ved holdskifte gemmes tidligere evalueringer som historik på spilleren og slettes med spilleren.

- **Beskeder:** klub-/holdbeskeder (fri tekst, afsendernavn, tidspunkt) gemmes i indbakken, til de slettes af afsender/klubadministrator, og slettes med holdet. Valgfri e-mail sendes via den konfigurerede SMTP-udbyder til trænernes egne adresser.

- **Forældresamtaler og motivation over tid:** samtalenoter og målinger tilhører spilleren (indgår i eksport, slettes med spilleren/ved opbevaringsfristen). Noter og aftaler vises aldrig for forældre; kun hjemmeøvelsen står på forældrerapporten.
