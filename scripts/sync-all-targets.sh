#!/usr/bin/env bash
# Sync Windows checkout -> WSL home, Windows citevision-v2 mirror, and C:\Citevision runtime.
set -euo pipefail

SRC="${1:-/mnt/c/Users/gheno/citevision}"
TARGETS=(
  "${HOME}/citevision-v2"
  "/mnt/c/Users/gheno/citevision-v2"
  "/mnt/c/Citevision"
)

RSYNC_EXCLUDES=(
  --exclude node_modules
  --exclude ai-engine/.venv
  --exclude ai-engine/models/yolov8n.onnx
  --exclude ai-engine/models/yolov8n.pt
  --exclude ai-engine/models/secondary
  --exclude ai-engine/models/insightface/models/buffalo_l
  --exclude logs
  --exclude .env
  --exclude dist
  --exclude data/videos
  --exclude infra/data
  --exclude video-engine/build
  --exclude .git
  --exclude frontend/test-results
  --exclude backend/bin
  --exclude HTTP
  --exclude 'backend/qc'
  --exclude 'backend/query'
)

if [[ ! -d "$SRC" ]]; then
  echo "[FAIL] Source not found: $SRC" >&2
  exit 1
fi

for DEST in "${TARGETS[@]}"; do
  echo "==> Syncing $SRC -> $DEST"
  mkdir -p "$DEST"
  # Protect destination demo/transcoded videos from --delete (excluded from source transfer).
  rsync -a --delete --no-group --no-owner \
    --filter 'P data/videos/' \
    --filter 'P ai-engine/models/secondary/' \
    --filter 'P ai-engine/models/insightface/' \
    "${RSYNC_EXCLUDES[@]}" "$SRC/" "$DEST/"
  find "$DEST/scripts" -name '*.sh' -exec sed -i 's/\r$//' {} + 2>/dev/null || true
  if [[ -f "$DEST/scripts/fix-crlf.py" ]]; then
    python3 "$DEST/scripts/fix-crlf.py" "$DEST/scripts/"*.sh 2>/dev/null || true
  fi
  echo "[OK] $DEST"
done

echo "=== All targets synced ==="
