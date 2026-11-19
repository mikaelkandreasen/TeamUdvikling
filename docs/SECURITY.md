# Sikkerhed – pentest og hærdning (v0.2.1)

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

## Kontroller der bestod (testet)
Alle ruter kræver login og 2FA (`pw_ok`-session kan ikke springe 2FA over); alle POST kræver CSRF; trænere kan ikke nå admin eller andre holds spillere (IDOR-sweep over alle ruter); lagret XSS escapes på alle sider; SQL-injektion i login; brugeropremsning (ens svar for ukendt/kendt bruger); replay af TOTP-kode; upload af SVG/forklædte filer afvises; 413 ved for store forespørgsler; ingen stacktraces.

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
- TOTP-hemmeligheder ligger i klartekst i databasen (og i backups). Beskyt volumen og backups; kryptering i hvile står i backloggen (B-012).
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
