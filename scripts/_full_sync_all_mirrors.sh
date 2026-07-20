#!/usr/bin/env bash
# Sync C:\Users\gheno\citevision -> 4 mirrors, align git to source HEAD.
set -euo pipefail
SRC="/mnt/c/Users/gheno/citevision"
COMMIT="$(git -C "$SRC" rev-parse --short HEAD)"
FULL="$(git -C "$SRC" rev-parse HEAD)"

EXCLUDES=(
  --exclude='.env'
  --exclude='.venv/'
  --exclude='node_modules/'
  --exclude='__pycache__/'
  --exclude='*.pyc'
  --exclude='data/videos/*.mp4'
  --exclude='data/videos/*.avi'
  --exclude='logs/'
  --exclude='.service_account'
  --exclude='backend/bin/'
  --exclude='ai-engine/models/'
  --exclude='*.pid'
  --exclude='infra/frigate-config/model_cache/'
  --exclude='infra/data/'
)

TARGETS=(
  "$HOME/citevision-v2"
  "/mnt/c/Users/gheno/citevision-v2"
  "/mnt/c/Citevision"
  "/mnt/c/Users/gheno/citevision_optimized"
)

echo "=== Sync from $SRC ($COMMIT) ==="
for DST in "${TARGETS[@]}"; do
  echo "--- $DST ---"
  if [ ! -d "$DST" ]; then
    echo "[SKIP] missing"
    continue
  fi
  rsync -a --delete "${EXCLUDES[@]}" "$SRC/" "$DST/" || true
  find "$DST" -maxdepth 4 -type f \( -name '*.sh' -o -name '*.py' \) -exec sed -i 's/\r$//' {} + 2>/dev/null || true
  if [ -d "$DST/.git" ]; then
    git -C "$DST" fetch origin 2>/dev/null || true
    git -C "$DST" checkout main 2>/dev/null || true
    git -C "$DST" reset --hard "$FULL" 2>/dev/null && echo "[OK] git=$COMMIT" || echo "[WARN] git reset failed"
  else
    echo "[OK] files only (no .git)"
  fi
  test -f "$DST/launcher/Heal-DiskC.ps1" && echo "[OK] Heal-DiskC.ps1" || echo "[FAIL] Heal missing"
done
echo "DONE"
for DST in "${TARGETS[@]}"; do
  if [ -d "$DST/.git" ]; then
    echo "$DST -> $(git -C "$DST" log -1 --oneline 2>/dev/null || echo ?)"
  elif [ -d "$DST" ]; then
    echo "$DST -> files (no git)"
  fi
done
