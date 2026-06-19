#!/usr/bin/env bash
# Copy project from Windows mount into WSL home for fast I/O
# Usage: bash scripts/sync-to-wsl.sh [WIN_SRC]
set -euo pipefail

if [[ -n "${1:-}" ]]; then
  WIN_SRC="$1"
elif [[ -n "${WIN_SRC:-}" ]]; then
  :
else
  # Default: parent of scripts/ on /mnt/c when invoked from drvfs checkout
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  WIN_SRC="$(dirname "$SCRIPT_DIR")"
  if [[ "$WIN_SRC" != /mnt/* ]]; then
    WIN_SRC="/mnt/c/Users/gheno/citevision-v2"
  fi
fi

DEST="${DEST:-${HOME}/citevision-v2}"

if [[ ! -d "$WIN_SRC" ]]; then
  echo "Windows source not found: $WIN_SRC" >&2
  exit 1
fi

echo "==> Syncing $WIN_SRC -> $DEST"
mkdir -p "$DEST"
rsync -a --delete \
  --exclude node_modules \
  --exclude ai-engine/.venv \
  --exclude ai-engine/models/yolov8n.onnx \
  --exclude ai-engine/models/yolov8n.pt \
  --exclude logs \
  --exclude .env \
  --exclude dist \
  --exclude data/videos \
  --exclude video-engine/build \
  "$WIN_SRC/" "$DEST/"

find "$DEST/scripts" -name '*.sh' -exec perl -pi -e 's/\r$//' {} + 2>/dev/null || true
find "$DEST/scripts" -name '*.sh' -exec sed -i '1s/^\xEF\xBB\xBF//' {} + 2>/dev/null || true

echo "[OK] Project at $DEST"
echo "Next:"
echo "  cd $DEST"
echo "  bash scripts/setup-wsl.sh"
echo "  bash scripts/start-linux.sh"
