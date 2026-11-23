#!/usr/bin/env bash
# Pakker hele arbejdsmappen INKL. .git (historik + tags) til en zip, som kan lægges oven i den lokale repo-mappe.
# Brug: scripts/package.sh [udmappe]   → <udmappe>/teamudvikling-<version>.zip  (standard udmappe: /home/claude/out)
set -euo pipefail
cd "$(dirname "$0")/.."
out="${1:-/home/claude/out}"; mkdir -p "$out"
ver="$(cat VERSION)"; zip_path="$out/teamudvikling-$ver.zip"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp/TeamUdvikling"
tar --exclude=.venv --exclude=data --exclude=__pycache__ --exclude=.pytest_cache --exclude=.env --exclude='*.db' --exclude='*.db-wal' --exclude='*.db-shm' -cf - . | tar -xf - -C "$tmp/TeamUdvikling"
rm -f "$zip_path"; (cd "$tmp" && zip -qr "$zip_path" TeamUdvikling)
echo "Pakket: $zip_path (med .git)"
