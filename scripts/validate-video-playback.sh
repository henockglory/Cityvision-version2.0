#!/usr/bin/env bash
set -euo pipefail
GO2RTC="${GO2RTC_URL:-http://localhost:1984}"
STREAM="${GO2RTC_STREAM:-benedicte}"
RTSP="${RTSP_URL:-rtsp://127.0.0.1:8554/$STREAM}"
PROBE_OUT="${TMPDIR:-/tmp}/go2rtc-probe-$$.ts"

echo "==> Video playback validation (go2rtc)"

STREAMS=$(curl -sf "$GO2RTC/api/streams" 2>/dev/null || echo '{}')
if ! echo "$STREAMS" | python3 -c "
import sys, json
d = json.load(sys.stdin)
sys.exit(0 if '$STREAM' in d else 1)
" 2>/dev/null; then
  echo "[FAIL] Stream '$STREAM' not registered in go2rtc"
  exit 1
fi
echo "[OK] Stream '$STREAM' registered"

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q citevision-v2-go2rtc; then
  if ! docker exec citevision-v2-go2rtc test -s /videos/benedicte_stream.mp4 2>/dev/null; then
    echo "[FAIL] /videos/benedicte_stream.mp4 missing in go2rtc container"
    echo "Run: bash scripts/fix-go2rtc-video.sh"
    exit 1
  fi
  echo "[OK] benedicte_stream.mp4 present in container"
fi

echo "==> RTSP probe (3 s)…"
rm -f "$PROBE_OUT"
if ! ffmpeg -y -hide_banner -loglevel error -rtsp_transport tcp \
  -i "$RTSP" -t 3 -c copy -an "$PROBE_OUT" 2>/dev/null; then
  echo "[FAIL] RTSP read failed for $RTSP"
  exit 1
fi
SIZE=$(stat -c%s "$PROBE_OUT" 2>/dev/null || stat -f%z "$PROBE_OUT")
rm -f "$PROBE_OUT"
if [[ "${SIZE:-0}" -lt 50000 ]]; then
  echo "[FAIL] RTSP probe too small (${SIZE} bytes) — flux inactif"
  exit 1
fi
echo "[OK] RTSP probe OK (${SIZE} bytes / 3s)"

CODE=$(curl -sf -o /dev/null -w '%{http_code}' "$GO2RTC/stream.html?src=$STREAM" || echo "000")
if [[ "$CODE" != "200" ]]; then
  echo "[FAIL] stream.html HTTP $CODE"
  exit 1
fi
echo "[OK] WebRTC player page HTTP 200"

echo "[OK] Video playback validation passed"
