# Sikkerhed – pentest og hærdning

Hvad der er gjort: white-box pentest af hele koden med automatiske angrebstests (`tests/test_security.py`, kører i CI ved hver ændring). Der er **ikke** udført en ekstern pentest fra internettet, og Docker-image/CI er ikke kørt i udviklingsmiljøet. Anbefal en ekstern scanning (fx `nuclei`/OWASP ZAP) mod det udrullede system, inden det åbnes mod internettet.

## Fund og rettelser
| # | Fund | Alvor | Rettelse |
|---|------|-------|----------|
| 1 | `/setup` var åben for den første besøgende, hvis `SETUP_TOKEN` ikke var sat (overtagelse af systemet på internettet) | Kritisk | Engangskode genereres automatisk (`/data/setup_token`, vises i log), kræves altid, slettes efter brug |
| 2 | Login-spærre kun pr. brugernavn: ingen IP-begrænsning (password spraying) og mulighed for at låse andres konti | Høj | Spærre pr. IP (20 fejl/10 min → 429), delt mellem workers via SQLite; `TRUSTED_PROXIES` giver ægte IP bag proxy |
| 3 | Stjålne sessionscookies forblev gyldige efter skift af adgangskode / nulstilling af 2FA | Høj | Session bindes til nøglet hash af adgangskoden; 2FA-nulstilling afbryder aktive sessioner |
| 4 | Excel-eksport kunne indeholde formler fra brugerindtastede navne/noter (formel-injektion) | Mellem | Celler der starter med `= + - @` gemmes som ren tekst |
| 5 | Gendannelseskoder: 32 bit og ren SHA-256 (offline-gæt ved databaselæk) | Mellem | 48 bit og HMAC-hash nøglet med serverens hemmelighed |
| 6 | Åben redirect via `next` med `\` | Lav | Streng validering af `next` |
| 7 | Manglende HSTS, Permissions-Policy, COOP/CORP; cookie uden `__Host-`-præfiks; `/healthz` viste version | Lav | Tilføjet (HSTS og `__Host-` når `COOKIE_SECURE=1`); `/healthz` viser kun status |
| 8 | Backup/audit-log voksede uden grænse; uafhængige afhængigheder ikke låst | Lav | Audit slettes efter 12 mdr.; afhængigheder fastlåst; Dependabot, `pip-audit` og `bandit` i CI |

## Simuleret angreb på login bag Cloudflare (v0.6.1)
`tests/test_login_attack.py` (25 angreb) kører appen som i drift (`TRUSTED_PROXIES=1`, sikre `__Host-`-cookies) bag en simuleret Cloudflare, der sætter `X-Forwarded-Proto` og tilføjer klientens rigtige IP sidst i `X-Forwarded-For`. Det er en lokal simulation – ikke et angreb på den rigtige side eller på Cloudflares kant.
| # | Fund | Alvor | Rettelse |
|---|------|-------|----------|
| 9 | **Lås-DoS:** 5 forkerte forsøg fra hvem som helst låste kontoen (fx `admin`) for alle i 10 min – gentaget i evighed | Høj | Låsning pr. (bruger, IP): 5 fejl spærrer kun den IP; 25 fejl fra alle IP'er låser kontoen for alle (`app/lockout.py`) |
| 10 | **Brugeropremsning via tid:** låste konti svarede uden at hashe adgangskoden (hurtigere end ukendte) | Mellem | Adgangskoden hashes altid, også for låste og ukendte brugere |
| 11 | **Session-cookie virkede efter log ud** (signeret, statsløs cookie kunne genafspilles) | Mellem | Hver session har et id; log ud (og udløb af admin-friskhed, låsning) sætter det på en afvisningsliste (`revoked_sessions`) |
| 12 | **Samtidig genbrug af 2FA-kode** (tjek-og-opdatér var ikke atomisk) | Mellem | `UPDATE … WHERE last_totp_step < ?` – kun én forespørgsel kan bruge et tidstrin |
| 13 | Login-siden kunne indekseres af søgemaskiner og viste versionsnummer til anonyme | Lav | `X-Robots-Tag: noindex`, version kun for indloggede |
| 14 | Meget lange brugernavne/adgangskoder (CPU/log) | Lav | Maks. 150/1024 tegn; afvises uden at hashe kandidaten |
| 15 | `COOKIE_SECURE=1` uden `TRUSTED_PROXIES` giver alle brugere én fælles IP-spærre (en angriber blokerer alle) | Mellem | Advarsel i loggen ved opstart |
Modstod angrebet: falsk `X-Forwarded-For` (appen bruger kun det sidste led, som Cloudflare tilføjer), brute force på 2FA, 9 åbne-redirect-varianter, login-CSRF, forfalskede/ændrede cookies, fejlsider uden lækage, cookie-flag (`Secure`, `HttpOnly`, `SameSite=Lax`, `__Host-`).
Vurderet og ikke indført: `ALLOWED_HOSTS`/origin-hemmelighed (tunnelen gør originen utilgængelig fra internettet; links i mails bruger `PUBLIC_URL`); tjek mod lækkede adgangskoder (kræver ekstern tjeneste).

### Cloudflare-indstillinger (gør dette)
1. **Ingen Access-login** på `teamudvikling.saem.dk` (appen har egen adgangskode + 2FA), men behold resten af beskyttelsen.
2. **Rate limiting-regel:** sti `/login` og `/nulstil`, maks. 10 forespørgsler/minut pr. IP, handling Block. (Appen har egen spærre, men Cloudflare stopper trafikken, før den rammer din NUC.)
3. **Bot Fight Mode** til. **Always Use HTTPS** til. Minimum TLS 1.2.
4. **Slå fra:** Rocket Loader, Email Address Obfuscation og Web Analytics-injektion. De indsætter scripts i siden, som appens CSP (`script-src 'self'`) blokerer, og det giver fejl.
5. **Cache:** lad HTML være uden for cache (standard). Brug ikke «Cache Everything» på domænet.
6. **Hold porten lukket:** `cloudflared` på NUC .235 er den eneste vej ind. Port 1020 på .212 må ikke videresendes i routeren.
7. Sæt `COOKIE_SECURE=1` og `TRUSTED_PROXIES=1` i stack'en. Loggen advarer ved opstart, hvis `TRUSTED_PROXIES` mangler.

## Kontroller der bestod (testet)
Alle ruter kræver login og 2FA (`pw_ok`-session kan ikke springe 2FA over); alle POST kræver CSRF; trænere kan ikke nå admin eller andre holds spillere (IDOR-sweep over alle ruter); lagret XSS escapes på alle sider; SQL-injektion i login; brugeropremsning (ens svar for ukendt/kendt bruger); replay af TOTP-kode; upload af SVG/forklædte filer afvises; 413 ved for store forespørgsler; ingen stacktraces.

## Roller, klubber og invitationer (v0.9.0)
- Roller: systemadministrator (`admin`), klubadministrator (`clubadmin`, kun egen klub), træner. Adgang til hold: træner via tildeling **og** samme klub; klubadministrator alle hold i egen klub; systemadministrator alle.
- Klubadministratorer kan ikke se eller ændre brugere/hold/profil i andre klubber (404), ikke oprette administratorer og ikke åbne systemsider (backup, eksport, audit, brug, klubber, backlog).
- Invitationer: 256-bit token (kun HMAC-hash gemmes), 7 dages levetid, engangsbrug (atomisk), kan tilbagekaldes, kræver afsenderens friske 2FA-kode, rate-begrænset pr. IP. Nye brugere skal sætte 2FA op, før de får adgang. Link-GET forbruger ikke tokenet.
- Cloudflare: tilføj `/invitation` til rate-limit-reglen sammen med `/login` og `/nulstil`.

## Spillerbilleder (v0.7.0)
- Upload kræver samtykke-afkrydsning; maks. 12 MB og 40 mio. pixel; kun JPEG/PNG/WebP (indholdet åbnes og genkodes – filendelse/type fra klienten stoles ikke på). SVG/HTML/GIF/afkortede filer afvises. EXIF, GPS og farveprofil fjernes ved genkodning.
- Leveres kun via hold-afgrænset endpoint (404 for andre hold), kræver login, `Cache-Control: no-store`. Revisionsloggen får kun «foto gemt/slettet», aldrig billeddata.

## Husk denne enhed (30 dage)
Valgfrit flueben efter fuldt login. Afvejning: bekvemmelighed mod, at en stjålet/ulåst enhed giver adgang til børnedata uden 2FA.
Modforanstaltninger: fast 30-dages udløb (ikke glidende); 256-bit token i HttpOnly/SameSite-cookie, kun nøglet hash i databasen; rotation ved hver brug og tyveridetektion (genbrug af gammelt token tilbagekalder alle enheder); tilbagekaldelse ved log ud, skift af adgangskode, 2FA-nulstilling og "Glem alle enheder"; **administration kræver altid frisk login med kode** (trin-op, 8 timer); højst 10 enheder pr. bruger. Slå funktionen fra med `REMEMBER_DAYS=0`. Anbefaling: aktivér skærmlås på de enheder, der huskes.

## Nulstilling af adgangskode/2FA via e-mail
Kun en administrator kan udløse en mail, og kun efter at have indtastet en **frisk 2FA-kode** (replay-beskyttet; fejl tæller som mislykket login og kan låse administratorens konto). Der er ingen offentlig «glemt adgangskode»-formular, så den kan ikke bruges til at opremse konti eller spamme.
Link: 256-bit engangstoken, kun HMAC-hash i databasen, 60 minutters levetid, maks. 3 mails pr. bruger pr. time; nyt link ugyldiggør det gamle. Linket bygges af `PUBLIC_URL` (aldrig Host-headeren, så linket ikke kan forgiftes). Åbning af linket (GET) forbruger intet, så mailscannere gør ingen skade; kun POST gennemfører. Linket kan ikke bruges, hvis adgangskoden skiftes eller e-mailadressen ændres imens.
- **Adgangskode:** nyt kodeord efter linket; 2FA kræves stadig ved login. Husk-enheder tilbagekaldes.
- **2FA:** linket alene er ikke nok – brugerens nuværende adgangskode kræves også (fejl tæller mod kontolåsning og IP-spærre). Derefter oprettes ny 2FA og nye gendannelseskoder; gamle koder og husk-enheder dør.
- Revisionsloggen får kun handling og formål (ikke token, ikke e-mailadresse). SMTP-adgangskoden ligger kun i miljøvariablen `SMTP_PASSWORD`.
Restrisiko: mailen sendes via den SMTP-udbyder, du vælger (databehandler). Brug TLS (`starttls`/`ssl`).

## Kendte restrisici (accepteret / backlog)
- TOTP-hemmeligheder er krypteret i databasen (Fernet, `enc1:`). Nøglen (`TOTP_KEY` eller `/data/totp_key`) skal sikres separat fra backups; mistes den, skal 2FA nulstilles. Sikkerhedslog (`/admin/security`) gemmer hændelser og IP i 30 dage. Valgfri tjek af lækkede adgangskoder (`PWNED_CHECK=1`, sender kun de første 5 tegn af en hash). iCal-hentning: https-only, offentlig IP; rest-risiko ved DNS-rebinding accepteret (D-016).
- CSP tillader `style-src 'unsafe-inline'` (inline `style=`-attributter). Scripts er strengt `self`.
- Nulstilling via e-mail findes kun som admin-godkendt handling (ingen offentlig «glemt adgangskode»); se afsnittet nedenfor. En kompromitteret postkasse kan kun nulstille adgangskoden, aldrig omgå 2FA.
- Sessioner er signerede cookies (ikke server-side); idle-timeout 45 min, maks. 8 timer.

## Internet-checkliste (skal være opfyldt, før porten åbnes)
1. Kør **kun** bag HTTPS-reverse proxy (Caddy / Nginx Proxy Manager / Traefik). Åbn ikke port 1020 direkte mod internettet; sæt `U11_BIND=127.0.0.1` hvis proxyen er på samme maskine.
2. `COOKIE_SECURE=1`, `TRUSTED_PROXIES=1`, fast `SECRET_KEY` (32+ tilfældige bytes).
3. Proxyen skal sætte `X-Forwarded-For` og `X-Forwarded-Proto` og fjerne tilsvarende headers fra klienten.
4. Brug en dedikeret firewallregel (kun 443 udad). Overvej IP-begrænsning/VPN (fx Tailscale/Cloudflare Access), da dataene er børns oplysninger – det er den stærkeste beskyttelse.
5. Opret administrator med det samme efter første start (opsætningskoden står i loggen), og sæt 2FA op.
6. Tag backup af volumen `u11-data` krypteret, og test gendannelse (B-004).
7. Hold afhængigheder opdateret (Dependabot) og redeploy ved sikkerhedsopdateringer.

## Chef-trænere og invitationer (v0.10.0)
- Chef-trænere (tabellen `team_heads`) kan kun ændre indstillinger/runder og invitere til **egne hold** i egen klub; de kan ikke invitere klubadministratorer, se andres invitationer eller åbne bruger-/klubsider. Afsendelse kræver stadig egen 2FA-kode.
- Brugernavn-tjekket (`/invitation/<token>/brugernavn`) kræver et gyldigt invitationslink og er IP-begrænset, så det ikke kan bruges til at opregne brugernavne. Ledigt-tjek gentages ved oprettelsen.
- **Spillerlink** (`/svar/<token>`): offentlig, men kræver et 256-bit token (kun HMAC-hash gemmes), udløber efter 7 dage, kan kun bruges én gang (atomisk), GET forbruger ikke linket, ugyldige forsøg tæller mod IP-begrænsningen, og siden viser kun fornavn og dette ene skema. Tilføj `/svar` til Cloudflare-rate-limit-reglen.
- **Assistent** (`users.readonly`) blokeres globalt for alle ændringer undtagen egen konto (adgangskode/2FA).
- «Alle brugere» (oprettet, senest logget ind) er kun for systemadministratorer.


## Sikkerhedsgennemgang 3 (2026-11-22, v0.29.0)
Gennemgået: offentlige ruter, CSRF/gate, skrivespærrer, SQL-opbygning, `|safe`/Markup, filhåndtering, ny kode siden v0.25 (e-mail-kø, kampforslag fra iCal, opstillingsforslag, sprogvalg, delvise opdateringer) og kendte sårbarheder i afhængighederne.

Rettet:
- **Afhængigheder:** Pillow < 13.0.0 har flere sårbarheder (bl.a. heap-overløb ved JPEG-afkodning; I behandler uploadede fotos) → `Pillow>=13`. gunicorn ≤ 25.3.0 har request smuggling → `gunicorn>=26`. `cryptography>=50` (tidligere tilladte versioner havde kendte fejl). `defusedxml` tilføjet, så openpyxl læser Excel-importen sikkert.
- **Billeder:** `Image.open(..., formats=JPEG/PNG/WEBP)` – Pillows parsere for andre formater (PSD, TIFF, BMP …) køres aldrig, heller ikke for at læse headeren.
- **Åben omdirigering i sprogvalg:** `next` med tab/linjeskift (`/\t/evil.example`) kunne af browseren læses som `//evil.example`. Bruger nu samme `_safe_next` som login.
- **DNS-rebinding i kalenderhentning:** værten blev slået op ved kontrollen og igen ved forbindelsen. Nu forbindes til den kontrollerede IP (certifikat tjekkes stadig mod værtsnavnet); kontroltegn i URL afvises.
- **Udgående kald:** kampforslag henter højst kalenderen én gang pr. minut pr. hold (ellers genbruges sidste hentning).
- **CI:** `pip-audit` blokerer nu udgivelse af Docker-imaget (før kun en advarsel).

Ikke fundet: SQL-injektion (dynamiske kolonnenavne kommer fra faste lister), XSS (al brugertekst autoescapes; Markup kun til server-genererede SVG med escapede værdier), manglende adgangskontrol (rutetest + ratchet-test grønne).

Ikke verificeret her (ingen netværk): at Pillow 13/gunicorn 26 installeres og kører i imaget – CI-røgtesten fanger det ved første push. Bandit/pip-audit køres i CI, ikke lokalt.

## Rettelse 2026-11-22 (v0.32.0): import afgrænset til klub
`importer.classify/apply` slog hold op med `SELECT … FROM teams` uden klub. En klubadministrator kunne derfor ramme et hold med samme navn i en anden klub (opdatere/oprette spillere), og nye hold kom i standardklubben. Nu tager begge funktioner `club_id`; klubben gemmes i forhåndsvisningen og kontrolleres igen ved bekræftelse. Isolationstest: `test_import_is_scoped_to_own_club`.
