#!/usr/bin/env bash
# Sync Windows repo -> WSL citevision-v2 and strip CRLF.
set -euo pipefail
WIN=/mnt/c/Users/gheno/citevision
WSL=$HOME/citevision-v2
mkdir -p "$WSL/scripts/microtest"
rsync -a --delete \
  "$WIN/ai-engine/src/citevision_ai/" "$WSL/ai-engine/src/citevision_ai/"
rsync -a "$WIN/ai-engine/tests/" "$WSL/ai-engine/tests/"
rsync -a "$WIN/scripts/microtest/" "$WSL/scripts/microtest/"
for f in "$WSL/scripts/microtest/"*.sh "$WSL/scripts/microtest/"*.py; do
  [ -f "$f" ] && sed -i 's/\r$//' "$f" && chmod +x "$f" 2>/dev/null || true
done
cp -f "$WIN/docs/MICROTEST-BATTERY-1HIT-GEMINI.md" "$WSL/docs/" 2>/dev/null || mkdir -p "$WSL/docs" && cp -f "$WIN/docs/MICROTEST-BATTERY-1HIT-GEMINI.md" "$WSL/docs/"
echo "synced to $WSL"
