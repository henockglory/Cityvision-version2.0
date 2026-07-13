#!/usr/bin/env bash
set -euo pipefail
SRC="${1:-/mnt/c/Users/gheno/citevision}"
TARGETS=(
  "${HOME}/citevision-v2"
  "/mnt/c/Users/gheno/citevision-v2"
  "/mnt/c/Citevision"
)
EX=(
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
  --exclude infra/frigate-config/model_cache
  --exclude video-engine/build
  --exclude .git
  --exclude frontend/test-results
  --exclude backend/bin
  --exclude rules-engine/bin
  --exclude HTTP
  --exclude 'backend/qc'
  --exclude 'backend/query'
)
for DEST in "${TARGETS[@]}"; do
  echo "==> Sync $SRC -> $DEST"
  mkdir -p "$DEST"
  rsync -a --no-group --no-owner "${EX[@]}" "$SRC/" "$DEST/"
  find "$DEST/scripts" -name '*.sh' -exec sed -i 's/\r$//' {} + 2>/dev/null || true
  find "$DEST" -type f \( -name '*.py' -o -name '*.go' -o -name '*.sql' \) -exec sed -i 's/\r$//' {} + 2>/dev/null || true
  echo "[OK] $DEST"
done
echo "=== SYNC COMPLETE ==="
