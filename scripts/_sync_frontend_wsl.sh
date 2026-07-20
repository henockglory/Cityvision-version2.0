#!/usr/bin/env bash
set -euo pipefail
WIN=/mnt/c/Users/gheno/citevision
DEST=~/citevision-v2
rsync -a --exclude node_modules --exclude dist \
  "$WIN/frontend/src/" "$DEST/frontend/src/"
echo "[OK] frontend/src synced"
if grep -q phone_use "$DEST/frontend/src/lib/modelImportTemplates.ts" 2>/dev/null; then
  echo "[WARN] old phone_use still in WSL file"
  exit 1
fi
echo "[OK] modelImportTemplates neutral"
