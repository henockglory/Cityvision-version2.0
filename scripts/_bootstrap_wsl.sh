#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

WIN_SRC="/mnt/c/Users/gheno/citevision"
DEST="$HOME/citevision-v2"

echo "=== Sync Windows -> WSL ==="
bash "$WIN_SRC/scripts/sync-to-wsl.sh" "$WIN_SRC"

# .env excluded by sync — copy if present on Windows
if [[ -f "$WIN_SRC/.env" ]]; then
  cp "$WIN_SRC/.env" "$DEST/.env"
  echo "[OK] .env copied from Windows"
fi

# Demo videos (excluded by sync)
if [[ -d "$WIN_SRC/data/videos" ]]; then
  mkdir -p "$DEST/data/videos"
  rsync -a "$WIN_SRC/data/videos/" "$DEST/data/videos/"
  echo "[OK] demo videos synced"
fi

cd "$DEST"
echo "=== Project at $DEST ==="
ls -la | head -15
