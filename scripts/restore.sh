#!/usr/bin/env bash
# Gendan databasen fra en backupfil ind i Docker-volumen.
# Brug:  scripts/restore.sh teamudvikling-backup.db [volumenavn]     (standard: <projekt>_teamudvikling-data eller teamudvikling-data)
set -euo pipefail
file="${1:?Angiv backupfil}"
vol="${2:-$(docker volume ls -q | grep -E 'teamudvikling-data$' | head -1)}"
[[ -n "$vol" ]] || { echo "Kunne ikke finde volumen. Angiv navnet som andet argument."; exit 1; }
[[ "$(head -c 15 "$file")" == "SQLite format 3" ]] || { echo "Filen er ikke en SQLite-database."; exit 1; }
here="$(cd "$(dirname "$0")" && pwd)"
python3 "$here/verify-backup.py" "$file" || { echo "Backuppen bestod ikke kontrollen – gendanner ikke."; exit 1; }
echo "Stop containeren først:  docker stop teamudvikling"
read -r -p "Overskriv databasen i volumen '$vol'? [skriv ja] " ok
[[ "$ok" == "ja" ]] || exit 1
docker run --rm -v "$vol":/data -v "$(realpath "$file")":/restore.db:ro python:3.13-slim \
  sh -c '[ -f /data/teamudvikling.db ] && cp /data/teamudvikling.db /data/teamudvikling.db.before-restore; cp /restore.db /data/teamudvikling.db && rm -f /data/teamudvikling.db-wal /data/teamudvikling.db-shm && chown 10001:10001 /data/teamudvikling.db'
echo "Den gamle database er gemt som teamudvikling.db.before-restore i volumen."
echo "Gendannet. Start containeren:  docker start teamudvikling"
