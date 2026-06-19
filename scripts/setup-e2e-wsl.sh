#!/usr/bin/env bash
# Prépare WSL pour validation E2E complète (LF, sync, migration, venv smoke)
set -euo pipefail
SRC="${SRC:-/mnt/c/Users/gheno/citevision-v2}"
DST="${DST:-$HOME/citevision-v2}"
echo "=== setup-e2e-wsl ==="
mkdir -p "$DST"
# Sync léger (scripts + code, pas node_modules)
for d in scripts shared backend ai-engine frontend/src docs rules-engine Makefile; do
  mkdir -p "$DST/$(dirname "$d")" 2>/dev/null || true
  rsync -a --delete "$SRC/$d" "$DST/$(dirname "$d")/" 2>/dev/null || cp -a "$SRC/$d" "$DST/$d" 2>/dev/null || true
done
find "$DST/scripts" -name '*.sh' -exec sed -i 's/\r$//' {} + 2>/dev/null || true
chmod +x "$DST"/scripts/*.sh "$DST"/scripts/e2e/lib/*.sh 2>/dev/null || true
# Migration zone_kind
if docker ps --format '{{.Names}}' | grep -q citevision-v2-postgres; then
  docker exec -i citevision-v2-postgres psql -U citevision -d citevision \
    -c "ALTER TABLE zones ADD COLUMN IF NOT EXISTS zone_kind TEXT NOT NULL DEFAULT '';" 2>/dev/null || true
fi
# Venv ML
if [ ! -x "$DST/ai-engine/.venv/bin/python3" ]; then
  python3 -m venv "$DST/ai-engine/.venv"
fi
"$DST/ai-engine/.venv/bin/pip" install -q -U pip
"$DST/ai-engine/.venv/bin/pip" install -q -e "$DST/ai-engine/.[identity,anpr,dev]"
echo "[OK] setup-e2e-wsl done"
