#!/usr/bin/env bash
# Fix demo video playback: VIDEOS_PATH, go2rtc recreate, stream repair, RTSP probe.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"

ENV_FILE="$(ensure_env_file "$ROOT")"
CANONICAL_VIDEOS="$ROOT/data/videos"

echo "=== Fix demo video playback ==="
echo "ROOT=$ROOT"

# 1. Fix VIDEOS_PATH in .env (must be WSL ext4 path, not /mnt/c)
if grep -q '^VIDEOS_PATH=' "$ENV_FILE" 2>/dev/null; then
  CURRENT=$(grep '^VIDEOS_PATH=' "$ENV_FILE" | cut -d= -f2- | tr -d '\r')
  if [[ "$CURRENT" != "$CANONICAL_VIDEOS" ]]; then
    echo "[FIX] VIDEOS_PATH: $CURRENT -> $CANONICAL_VIDEOS"
    sed -i "s|^VIDEOS_PATH=.*|VIDEOS_PATH=$CANONICAL_VIDEOS|" "$ENV_FILE"
  else
    echo "[OK] VIDEOS_PATH=$CURRENT"
  fi
else
  echo "[FIX] Adding VIDEOS_PATH=$CANONICAL_VIDEOS"
  echo "VIDEOS_PATH=$CANONICAL_VIDEOS" >> "$ENV_FILE"
fi

mkdir -p "$CANONICAL_VIDEOS/demo"
load_dotenv "$ENV_FILE"

# Restore transcoded demo MP4s if missing (often still on C:\Citevision runtime).
DEMO_ORG="${DEMO_ORG_ID:-e312f375-7442-4089-8022-ed232abc09e8}"
DEMO_DEST="$CANONICAL_VIDEOS/demo/$DEMO_ORG"
if ! compgen -G "$DEMO_DEST"/*_stream.mp4 >/dev/null 2>&1; then
  RESTORE_SRC="/mnt/c/Citevision/data/videos/demo/$DEMO_ORG"
  if [[ -d "$RESTORE_SRC" ]] && compgen -G "$RESTORE_SRC"/*_stream.mp4 >/dev/null 2>&1; then
    echo "[FIX] Restoring demo streams from $RESTORE_SRC"
    mkdir -p "$DEMO_DEST"
    cp -a "$RESTORE_SRC"/*_stream.mp4 "$DEMO_DEST/"
  else
    echo "[WARN] No demo *_stream.mp4 in $DEMO_DEST — re-import videos in Demo Center if playback fails"
  fi
fi

# 2. Ensure benedicte legacy stream + recreate go2rtc with correct mount
bash "$ROOT/scripts/ensure-demo-video.sh"
bash "$ROOT/scripts/fix-go2rtc-video.sh"

# 3. Trigger backend stream re-registration (restart api briefly or call ensure via health wait)
echo "==> Restarting backend to re-register demo streams in go2rtc"
LOGDIR="$ROOT/logs"
# shellcheck source=scripts/lib/env-utils.sh
stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
free_port "${API_PORT:-8081}"
sleep 2
GO_BIN="/usr/local/go/bin/go"
[[ -x "$GO_BIN" ]] || GO_BIN="$(command -v go)"
start_bg backend "$ROOT/backend" "$GO_BIN run ./cmd/api" "$LOGDIR" "$ENV_FILE"
for _ in $(seq 1 60); do
  if curl -sf "http://localhost:${API_PORT:-8081}/health" >/dev/null 2>&1; then
    echo "[OK] backend up"
    break
  fi
  sleep 2
done
sleep 3

echo "==> go2rtc streams"
curl -sf "http://localhost:${GO2RTC_PORT:-1984}/api/streams" | python3 -m json.tool | head -80

echo "==> Demo files in container"
docker exec citevision-v2-go2rtc ls -lahR /videos/demo/ 2>/dev/null | head -40 || echo "[WARN] no /videos/demo in container"

# 4. Find first demo stream name and probe RTSP
STREAM=$(curl -sf "http://localhost:${GO2RTC_PORT:-1984}/api/streams" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for k in sorted(d.keys()):
    if k.startswith('demo-'):
        print(k)
        break
" 2>/dev/null || true)

if [[ -n "${STREAM:-}" ]]; then
  echo "==> RTSP probe for $STREAM"
  if GO2RTC_STREAM="$STREAM" RTSP_URL="rtsp://127.0.0.1:8554/$STREAM" bash "$ROOT/scripts/validate-video-playback.sh"; then
    echo "[OK] Playback validation passed for $STREAM"
  else
    echo "[WARN] RTSP probe failed for $STREAM — check ffmpeg logs in go2rtc"
  fi
else
  echo "[WARN] No demo-* stream found — select a video in Demo Center UI"
  GO2RTC_STREAM=benedicte bash "$ROOT/scripts/validate-video-playback.sh" || true
fi

echo "=== Done ==="
echo "  Demo UI: http://localhost:5174/demo"
echo "  go2rtc:  http://localhost:1984/stream.html?src=${STREAM:-benedicte}&mode=webrtc,mse"
