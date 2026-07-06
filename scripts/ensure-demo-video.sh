#!/usr/bin/env bash
# [Opt-in] Prépare benedicte_stream.mp4 pour scripts démo legacy (Kinshasa).
# L'installation standard n'appelle PAS ce script — voir ensure-video-storage.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${CITEVISION_PREPARE_DEMO_VIDEO:-0}" != "1" ]]; then
  echo "[SKIP] ensure-demo-video.sh — opt-in uniquement (CITEVISION_PREPARE_DEMO_VIDEO=1)"
  echo "       Installation neutre : bash scripts/ensure-video-storage.sh"
  echo "       Téléversez vos vidéos via Demo Center / API upload."
  exit 0
fi

bash "$ROOT/scripts/prepare-demo-video.sh"

VIDEO_DST="$ROOT/data/videos/benedicte_stream.mp4"
echo "[OK] Demo stream video: $VIDEO_DST ($(du -h "$VIDEO_DST" 2>/dev/null | cut -f1 || echo '?'))"

ENV_FILE="$ROOT/.env"
if [[ -f "$ENV_FILE" ]]; then
  if grep -q '^VIDEOS_PATH=' "$ENV_FILE"; then
    sed -i "s|^VIDEOS_PATH=.*|VIDEOS_PATH=$ROOT/data/videos|" "$ENV_FILE" 2>/dev/null || true
  else
    echo "VIDEOS_PATH=$ROOT/data/videos" >> "$ENV_FILE"
  fi
  if grep -q '^DEMO_VIDEO_PATH=' "$ENV_FILE"; then
    sed -i "s|^DEMO_VIDEO_PATH=.*|DEMO_VIDEO_PATH=$VIDEO_DST|" "$ENV_FILE" 2>/dev/null || true
  else
    echo "DEMO_VIDEO_PATH=$VIDEO_DST" >> "$ENV_FILE"
  fi
fi

export VIDEOS_PATH="$ROOT/data/videos"
export DEMO_VIDEO_PATH="$VIDEO_DST"
