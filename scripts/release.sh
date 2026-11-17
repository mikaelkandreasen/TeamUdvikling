#!/usr/bin/env bash
# Udgiv en ny version:  scripts/release.sh 0.2.0
# 1) kører tests  2) opdaterer VERSION og CHANGELOG.md  3) committer og opretter tag vX.Y.Z
# Push derefter:  git push && git push --tags   (CI bygger og udgiver Docker-imaget)
set -euo pipefail
cd "$(dirname "$0")/.."

new="${1:-}"
[[ "$new" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Brug: $0 MAJOR.MINOR.PATCH (fx 0.2.0)"; exit 1; }
git diff --quiet && git diff --cached --quiet || { echo "Arbejdskopien har uncommittede ændringer."; exit 1; }
[[ "$(git rev-parse --abbrev-ref HEAD)" == "main" ]] || { echo "Udgiv kun fra main."; exit 1; }
git rev-parse "v$new" >/dev/null 2>&1 && { echo "Tag v$new findes allerede."; exit 1; }

python3 -m pytest -q

today="$(date +%F)"
python3 - "$new" "$today" <<'EOF'
import re, sys
new, today = sys.argv[1:3]
s = open("CHANGELOG.md", encoding="utf8").read()
assert "## [Unreleased]" in s, "CHANGELOG mangler '## [Unreleased]'"
s = s.replace("## [Unreleased]", f"## [Unreleased]\n\n## [{new}] - {today}", 1)
open("CHANGELOG.md", "w", encoding="utf8").write(s)
EOF
echo "$new" > VERSION
git add VERSION CHANGELOG.md
git commit -m "chore(release): v$new"
git tag -a "v$new" -m "Version $new"
echo "Klar. Kør: git push && git push --tags"
