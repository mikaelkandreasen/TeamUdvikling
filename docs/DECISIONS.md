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
