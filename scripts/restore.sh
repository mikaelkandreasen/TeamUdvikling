#!/usr/bin/env bash
# Gendan databasen fra en backupfil ind i Docker-volumen.
# Brug:  scripts/restore.sh u11-backup.db [volumenavn]     (standard: <projekt>_u11-data eller u11-data)
set -euo pipefail
file="${1:?Angiv backupfil}"
vol="${2:-$(docker volume ls -q | grep -E 'u11-data$' | head -1)}"
[[ -n "$vol" ]] || { echo "Kunne ikke finde volumen. Angiv navnet som andet argument."; exit 1; }
[[ "$(head -c 15 "$file")" == "SQLite format 3" ]] || { echo "Filen er ikke en SQLite-database."; exit 1; }
here="$(cd "$(dirname "$0")" && pwd)"
python3 "$here/verify-backup.py" "$file" || { echo "Backuppen bestod ikke kontrollen – gendanner ikke."; exit 1; }
echo "Stop containeren først:  docker stop u11-udvikling"
read -r -p "Overskriv databasen i volumen '$vol'? [skriv ja] " ok
[[ "$ok" == "ja" ]] || exit 1
docker run --rm -v "$vol":/data -v "$(realpath "$file")":/restore.db:ro python:3.13-slim \
  sh -c '[ -f /data/u11.db ] && cp /data/u11.db /data/u11.db.before-restore; cp /restore.db /data/u11.db && rm -f /data/u11.db-wal /data/u11.db-shm && chown 10001:10001 /data/u11.db'
echo "Den gamle database er gemt som u11.db.before-restore i volumen."
echo "Gendannet. Start containeren:  docker start u11-udvikling"
