#!/usr/bin/env bash
# Sync Windows citevision -> WSL runtime ~/citevision-v2 [P.138]
set -euo pipefail
SRC="${1:-/mnt/c/Users/gheno/citevision}"
DST="${2:-$HOME/citevision-v2}"
mkdir -p "$DST"
rsync -a \
  --exclude node_modules \
  --exclude .git \
  --exclude frontend/dist \
  --exclude 'ai-engine/.venv' \
  --exclude 'infra/data/videos' \
  "$SRC/" "$DST/"
find "$DST/backend" "$DST/ai-engine" "$DST/scripts" "$DST/frontend/src" -type f \
  \( -name '*.go' -o -name '*.py' -o -name '*.sh' -o -name '*.ts' -o -name '*.tsx' -o -name '*.json' \) \
  -exec sed -i 's/\r$//' {} + 2>/dev/null || true
echo "[OK] synced $SRC -> $DST"
