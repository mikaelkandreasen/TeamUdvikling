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
| Trænerkonti | navn, brugernavn, adgangskode-hash, 2FA-hemmelighed | Adgangskontrol | Trænere | Admin | Når trænere stopper |
| Logs | audit-log, loginforsøg | Sikkerhed/ansvarlighed | System | Admin | 12 mdr. / 1 time |

## 3. Retsgrundlag
Anbefalet: **samtykke fra forældremyndighedsindehaver** (art. 6(1)(a), art. 8) indhentet pr. barn, særskilt og kunne trækkes tilbage. Alternativ (legitim interesse, art. 6(1)(f)) er mere skrøbeligt, fordi det drejer sig om børns oplysninger, trivsel og vurderinger. Klubben skal vælge og dokumentere. Trivsel/motorik kan i visse tilfælde nærme sig helbredsoplysninger (art. 9) – hold dem **faktuelle og neutrale**, undgå diagnoser og følsomme beskrivelser i fritekstfelter.

## 4. Principper
- **Dataminimering:** ingen CPR-nr., ingen adresser, ingen billeder af børn, ingen forældredata. Fritekstfelter (noter, tiltag) må ikke bruges til følsomme oplysninger.
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
