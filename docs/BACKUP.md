# Backup og gendannelse

## Hvad tages backup af?
- **Automatisk:** én backup pr. døgn (ved første login efter 24 timer) i `/data/backups`, de seneste 14 gemmes. Hver backup **kontrolleres** (integritet, fremmednøgler, skemaversion), og en ødelagt backup slettes i stedet for at fortrænge en god.
- **Manuelt:** *Administration → Hent backup* (systemadministrator).
- Backuppen er én SQLite-fil med alt: klubber, hold, brugere, spillere, evalueringer, billeder og logoer. `secret_key` ligger ved siden af i volumen og er **ikke** med i databasen: mister du den, logges alle ud, og åbne invitationer/nulstillinger virker ikke længere – data er upåvirket. Tag gerne en kopi af den sammen med backuppen, og opbevar den adskilt fra databasen.

## Kontrollér en backup (kan køres hvor som helst)
```bash
python3 scripts/verify-backup.py u11-20261121-030000.db
```
Kontrollen er kun-læsning og viser skemaversion og antal rækker.

## Gendan (Docker)
```bash
docker stop u11-udvikling
scripts/restore.sh u11-20261121-030000.db      # kontrollerer filen, gemmer den gamle som u11.db.before-restore
docker start u11-udvikling
```
Tjek bagefter: log ind, åbn *Spillere*, og se at `/healthz` svarer. Skemaet opgraderes automatisk, hvis backuppen er fra en ældre version. Backup fra en **nyere** version end appen afvises.

## Afprøv gendannelsen (gør det mindst hver 3. måned)
1. Hent en backup hjem fra off-site-lageret (ikke fra serveren).
2. `python3 scripts/verify-backup.py <fil>`.
3. Start en midlertidig container på en anden port med en tom volumen, kør `restore.sh <fil> <volumen>`, og log ind.
4. Slet den midlertidige container og volumen igen.

## Kopi uden for serveren (3-2-1)
Kopiér `/data/backups` til et andet sted end hjemmeserveren, fx hver nat.

**rclone (sky/NAS):** find volumen-stien med `docker volume inspect u11-data` (`Mountpoint`), og læg i `crontab -e` på værten:
```
30 3 * * * rclone copy /var/lib/docker/volumes/u11-data/_data/backups remote:team-udvikling-backup --max-age 3d
```
**rsync til NAS:**
```
30 3 * * * rsync -a /var/lib/docker/volumes/u11-data/_data/backups/ nas:/volume1/backup/team-udvikling/
```
Backups indeholder børns data: krypter dem på den eksterne lagerplads (`rclone crypt` eller krypteret volumen), og begræns adgangen. Slet gamle kopier efter samme frist som i GDPR-dokumentet.
