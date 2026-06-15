#!/usr/bin/env bash
# Garantit benedicte_stream.mp4 (sans B-frames) accessible par go2rtc sur /videos
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

bash "$ROOT/scripts/prepare-demo-video.sh"

VIDEO_DST="$ROOT/data/videos/benedicte_stream.mp4"
echo "[OK] Demo stream video: $VIDEO_DST ($(du -h "$VIDEO_DST" | cut -f1))"

# Met à jour .env pour Docker (chemin absolu WSL)
ENV_FILE="$ROOT/.env"
if [[ -f "$ENV_FILE" ]]; then
  if grep -q '^VIDEOS_PATH=' "$ENV_FILE"; then
    sed -i "s|^VIDEOS_PATH=.*|VIDEOS_PATH=$ROOT/data/videos|" "$ENV_FILE" 2>/dev/null || \
      perl -pi -e "s|^VIDEOS_PATH=.*|VIDEOS_PATH=$ROOT/data/videos|" "$ENV_FILE"
  else
    echo "VIDEOS_PATH=$ROOT/data/videos" >> "$ENV_FILE"
  fi
  if grep -q '^DEMO_VIDEO_PATH=' "$ENV_FILE"; then
    sed -i "s|^DEMO_VIDEO_PATH=.*|DEMO_VIDEO_PATH=$VIDEO_DST|" "$ENV_FILE" 2>/dev/null || \
      perl -pi -e "s|^DEMO_VIDEO_PATH=.*|DEMO_VIDEO_PATH=$VIDEO_DST|" "$ENV_FILE"
  else
    echo "DEMO_VIDEO_PATH=$VIDEO_DST" >> "$ENV_FILE"
  fi
  if grep -q '^PROJECT_ROOT=' "$ENV_FILE"; then
    sed -i "s|^PROJECT_ROOT=.*|PROJECT_ROOT=$ROOT|" "$ENV_FILE" 2>/dev/null || \
      perl -pi -e "s|^PROJECT_ROOT=.*|PROJECT_ROOT=$ROOT|" "$ENV_FILE"
  else
    echo "PROJECT_ROOT=$ROOT" >> "$ENV_FILE"
  fi
fi

export VIDEOS_PATH="$ROOT/data/videos"
export DEMO_VIDEO_PATH="$VIDEO_DST"
