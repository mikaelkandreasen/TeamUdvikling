# Backup og gendannelse

## Hvad tages backup af?
- **Automatisk:** én backup pr. døgn (ved første login efter 24 timer) i `/data/backups`, de seneste 14 gemmes. Hver backup **kontrolleres** (integritet, fremmednøgler, skemaversion), og en ødelagt backup slettes i stedet for at fortrænge en god.
- **Manuelt:** *Administration → Hent backup* (systemadministrator).
- Backuppen er én SQLite-fil med alt: klubber, hold, brugere, spillere, evalueringer, billeder og logoer. `secret_key` ligger ved siden af i volumen og er **ikke** med i databasen: mister du den, logges alle ud, og åbne invitationer/nulstillinger virker ikke længere – data er upåvirket. Tag gerne en kopi af den sammen med backuppen, og opbevar den adskilt fra databasen.

## Kontrollér en backup (kan køres hvor som helst)
```bash
python3 scripts/verify-backup.py teamudvikling-20261121-030000.db
```
Kontrollen er kun-læsning og viser skemaversion og antal rækker.

## Planlagt automatisk backup (v0.38.0)
Administration → Backup → «Automatisk backup efter plan» (kun systemadministrator): slå til, vælg ugedage, klokkeslæt (serverens tid, `TZ`) og hvor mange backups der gemmes (1–90). Appen tager højst én planlagt backup pr. dag, også med flere workers, og viser seneste kørsel, fejl og næste tidspunkt. Backup uden plan: mindst én pr. døgn som før.

**Til eksternt job:** efter hver backup (planlagt, manuel og daglig) opdateres to faste filer i `/data/backups`: `latest.db` (seneste backup) og `latest.json` (`file`, `size`, `created`, `sha256`). Lad et job på værten hente dem et stykke tid efter det planlagte tidspunkt, fx `rclone copy <volumen>/backups/latest.db remote:teamudvikling/ ` og tjek `sha256` i `latest.json`. Husk også `totp_key` (se nedenfor), som ikke ligger i backuppen.

## Gendan via siden (anbefalet)
Administration → Backup → **Gendan en backup**: vælg `.db`-filen, (hvis backuppen kommer fra en anden installation) også filen `totp_key` fra den gamle volumen, skriv din 2FA-kode og `GENDAN`. Den nuværende database gemmes først i `/data/backups`. Uden `totp_key` kan de gendannede brugere ikke bruge deres 2FA-kode, og 2FA skal nulstilles.

## Gendan (Docker)
```bash
docker stop teamudvikling
scripts/restore.sh teamudvikling-20261121-030000.db      # kontrollerer filen, gemmer den gamle som teamudvikling.db.before-restore
docker start teamudvikling
```
Tjek bagefter: log ind, åbn *Spillere*, og se at `/healthz` svarer. Skemaet opgraderes automatisk, hvis backuppen er fra en ældre version. Backup fra en **nyere** version end appen afvises.

## Afprøv gendannelsen (gør det mindst hver 3. måned)
1. Hent en backup hjem fra off-site-lageret (ikke fra serveren).
2. `python3 scripts/verify-backup.py <fil>`.
3. Start en midlertidig container på en anden port med en tom volumen, kør `restore.sh <fil> <volumen>`, og log ind.
4. Slet den midlertidige container og volumen igen.

## Kopi uden for serveren (3-2-1)
Kopiér `/data/backups` til et andet sted end hjemmeserveren, fx hver nat.

**rclone (sky/NAS):** find volumen-stien med `docker volume inspect teamudvikling-data` (`Mountpoint`), og læg i `crontab -e` på værten:
```
30 3 * * * rclone copy /var/lib/docker/volumes/teamudvikling-data/_data/backups remote:team-udvikling-backup --max-age 3d
```
**rsync til NAS:**
```
30 3 * * * rsync -a /var/lib/docker/volumes/teamudvikling-data/_data/backups/ nas:/volume1/backup/team-udvikling/
```
Backups indeholder børns data: krypter dem på den eksterne lagerplads (`rclone crypt` eller krypteret volumen), og begræns adgangen. Slet gamle kopier efter samme frist som i GDPR-dokumentet.

## TOTP-nøglen
TOTP-hemmeligheder er krypteret. Gem filen `/data/totp_key` (eller værdien af `TOTP_KEY`) et andet sted end databasebackups. Uden nøglen kan backuppen gendannes, men alle brugere skal have nulstillet 2FA.
