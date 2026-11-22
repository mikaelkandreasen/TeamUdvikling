# Migrationer

Skemaændringer styres af en lille migrationsrunner i `app/db.py` (`MIGRATIONS`, `run_migrations`).

**Sådan virker det**
- Hver migration har et fast id (`011_navn`) og kører præcis én gang pr. database. Kørte migrationer står i tabellen `schema_migrations`.
- Er der ventende migrationer på en eksisterende database, tages først en kopi `pre-migration-<tid>.db` i `/data/backups` (de 5 seneste gemmes ud over de daglige backups).
- Nye migrationer kører i en transaktion. Fejler en, rulles den tilbage, den logges ikke, og appen stopper med en tydelig fejl (databasen er uændret – gendan evt. kopien).
- De 10 første (`001`–`010`) er de gamle idempotente funktioner og kører uden ydre transaktion.

**Tilføj en migration**
1. Skriv en funktion `def _m011_navn(con): ...` med eksplicit SQL (`ALTER TABLE`, `CREATE TABLE`, dataændringer). Brug ikke `commit()` eller `executescript()` i den.
2. Tilføj `("011_navn", _m011_navn)` NEDERST i `MIGRATIONS`. Ændr eller omsortér aldrig eksisterende poster.
3. Øg `SCHEMA_VERSION` og tests (`tests/test_reset_mail.py`) og beskriv ændringen i CHANGELOG.
4. Nye tabeller må stadig oprettes i `SCHEMA` (`IF NOT EXISTS`), så en ny database får dem; migrationen sørger for gamle databaser.
5. Slet aldrig brugerdata i en migration uden at backuppen er taget (den tages automatisk).

**Test**: `tests/test_migrations.py` sikrer, at en ny og en gammel database ender med samme skema, at en migration kun kører én gang, og at en fejlende migration rulles tilbage.
