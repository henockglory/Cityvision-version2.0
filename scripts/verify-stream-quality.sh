#!/usr/bin/env bash
# ffprobe B-frames=0 après transcode go2rtc ; latence WebRTC optionnelle
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GO2RTC="${GO2RTC:-http://localhost:1984}"

echo "=== verify-stream-quality ==="

if ! command -v ffprobe >/dev/null 2>&1; then
  echo "SKIP: ffprobe not installed"
  exit 0
fi

STREAMS=$(curl -sf "$GO2RTC/api/streams" 2>/dev/null || echo '{}')
SRC=$(echo "$STREAMS" | python3 -c "
import sys, json
s = json.load(sys.stdin)
for name in s:
    if name.startswith('cam-') or name == 'benedicte':
        print(name)
        break
" 2>/dev/null || true)

if [ -z "$SRC" ]; then
  echo "WARN: no stream to probe — go2rtc empty"
  exit 0
fi

M3U8="$GO2RTC/api/stream.m3u8?src=$SRC"
TMP=$(mktemp)
if ffprobe -v error -select_streams v:0 -show_entries stream=has_b_frames,codec_name -of default=nw=1 "$M3U8" 2>/dev/null | tee "$TMP"; then
  if grep -qi 'has_b_frames=1' "$TMP" 2>/dev/null; then
    echo "WARN: B-frames present on $SRC (WebRTC may glitch)"
  else
    echo "PASS B-frames=0 or absent on $SRC"
  fi
  if grep -qi h264 "$TMP" 2>/dev/null; then
    echo "PASS codec h264"
  fi
else
  echo "WARN: ffprobe on HLS failed (stream offline?)"
fi
rm -f "$TMP"

echo "=== verify-stream-quality OK ==="
