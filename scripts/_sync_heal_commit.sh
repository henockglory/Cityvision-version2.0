#!/usr/bin/env bash
set -euo pipefail
SRC=/mnt/c/Users/gheno/citevision
COMMIT=$(git -C "$SRC" rev-parse HEAD)
SHORT=$(git -C "$SRC" rev-parse --short HEAD)
EXCLUDES=(
  --exclude='.env' --exclude='.venv/' --exclude='node_modules/'
  --exclude='__pycache__/' --exclude='logs/' --exclude='*.pid'
  --exclude='backend/bin/' --exclude='ai-engine/models/'
  --exclude='infra/frigate-config/model_cache/' --exclude='infra/data/'
  --exclude='data/videos/*.mp4'
)
echo "Sync to $SHORT"
# WSL runtime first (fast)
rsync -a --delete "${EXCLUDES[@]}" "$SRC/" "$HOME/citevision-v2/"
find "$HOME/citevision-v2" -maxdepth 4 -type f \( -name '*.sh' -o -name '*.py' \) -exec sed -i 's/\r$//' {} + 2>/dev/null || true
git -C "$HOME/citevision-v2" fetch origin 2>/dev/null || true
git -C "$HOME/citevision-v2" reset --hard "$COMMIT"
echo "[OK] $HOME/citevision-v2 -> $(git -C "$HOME/citevision-v2" log -1 --oneline)"
echo DONE_WSL
