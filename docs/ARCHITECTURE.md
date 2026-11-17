# Arkitektur

## Overblik
Flask-app (server-renderet, ingen frontend-framework) + SQLite i WAL-tilstand. Kører bag gunicorn i én container med et `/data`-volumen
(`u11.db`, `backups/`, `secret_key`). Diagrammer er server-genereret SVG (`charts.py`) – ingen JavaScript-afhængigheder.

## Request-flow (`app/__init__.py`)
`before_request`: ① `auth.load_user()` (session → bruger, idle-timeout 45 min) → ② `teams.resolve()` (adgangsliste + aktivt hold, valideret
hver gang) → ③ CSRF-tjek på POST → ④ `auth.gate()` (kræver fuldt login inkl. 2FA, tvungen adgangskodeskift, kræver hold).
Offentlige endpoints: `auth.login`, `auth.login_2fa`, `auth.setup`, `static`, `healthz`.

## Moduler
| Fil | Ansvar |
|---|---|
| `model.py` | Roller, færdigheder, 24 kriterier, standardspørgsmål; rene beregninger: `compute_round`, `load_rounds`, `area_development`, relativ alder |
| `db.py` | Skema, `init_db`, `seed_team`, `create_team`, indstillinger pr. hold (`t<id>:<nøgle>`), revisionslog, backup |
| `auth.py` | Login, 2FA-opsætning, gendannelseskoder, lockout, første opsætning (`/setup`), konto |
| `totp.py` | TOTP uden eksterne pakker (testet mod RFC 6238) |
| `teams.py` | `accessible_teams`, `resolve`, `switch` |
| `helpers.py` | `team_id()`, `active_players()`, `get_player()` (404 på fremmed hold), `round_info()` |
| `evaluation.py` | Evaluering, teamoversigt, udvikling, position/bane, områder, profil |
| `motivation.py` · `devdata.py` · `reports.py` · `players.py` · `admin.py` · `views.py` | Se modulets docstring |
| `charts.py` | `radar`, `line_chart`, `bars`, `pitch`, `heat` |

## Datamodel (SQLite)
```
teams(id, name, season)                      user_teams(user_id, team_id)
users(id, username, pw_hash, role, totp_*, failed_logins, locked_until, must_change_pw)   recovery_codes(user_id, code_hash, used)
players(id, team_id→teams, name, birth_date, position, position2, foot, focus1, focus2, notes, active)
evaluations(round 1-4, player_id→players, trainer_id→users, crit 0-23, score 1-5)  PK(round,player,trainer,crit)
motivation_categories(team_id, cat 0-2, title)   motivation_questions(team_id, qidx 0-21, cat, text)   motivation_answers(player_id, qidx, score)
devdata(player_id, trainings, matches, t1-t3, m1-m4, tiltag, eget_maal, followup, status)
settings(key='t<team_id>:<navn>', value)     audit_log(ts, user, action, detail)
```
Fremmednøgler er `ON DELETE CASCADE`: sletter man et hold/en spiller/en bruger, forsvinder tilhørende data.
`crit`-indeks = `rolle*6 + færdighed` (rolle: 0 boldholder … 3 støttespiller; færdighed: 0 teknik … 5 maskering).

## Beregningsregler (`model.compute_round`)
- Trænerens rolle-gennemsnit = gennemsnit af trænerens scores i rollen (tomme ignoreres).
- Holdets rolle-gennemsnit for en spiller = gennemsnit over trænernes rolle-gennemsnit. **Samlet** = gennemsnit af de fire rolle-gennemsnit.
- **Enighed** = største minus mindste samlede score mellem trænere (kræver ≥ 2). ≤ 1 høj enighed · ≤ 2 moderat forskel · derover stor forskel.
- Relativ alder: kvartal = (måned−1)//3+1; "måneder efter 1. januar" = måned−1 + (dag−1)/dage i måneden. Overvægt = ≥ 65 % født i 1. halvår; Q1-vs-Q4-forskel ≥ 0,5.

## Sikkerhedsmodel
- 2FA er obligatorisk; adgangskode ≥ 12 tegn (scrypt via werkzeug); 5 fejl → 10 min. lås; TOTP-trin kan ikke genbruges; gendannelseskoder gemmes som SHA-256.
- Sessionscookie: HttpOnly, SameSite=Lax, Secure via `COOKIE_SECURE=1`. CSRF-token pr. session. CSP uden inline scripts.
- Dataisolering mellem hold håndhæves i `helpers.get_player` og i alle aggregeringer (`load_rounds(db, team_id)`); testet i `tests/test_teams.py`.
- Persondata om børn: kør kun på LAN/VPN eller bag HTTPS; tag backup; informér forældre; slet via admin (GDPR); indsigt via JSON-eksport.

## Mobil
Mobile-first CSS (`static/style.css`): bundmenu < 900 px, sidemenu ≥ 900 px; tabeller bliver til kort < 700 px (`table.responsive` + `data-label`);
score-knapper er ≥ 48 px. `/m` er en mobilforside med store tiles; telefoner (UA indeholder "Mobi") sendes dertil fra `/`.

## Udvidelsespunkter
Nyt modul → blueprint i `app/`, registrér i `create_app`, skabeloner i `templates/`, tests i `tests/`, opdatér denne fil og `CHANGELOG.md`.
