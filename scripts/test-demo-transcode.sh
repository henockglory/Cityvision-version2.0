#!/usr/bin/env bash
# Quick smoke test: transcode raw demo file + register go2rtc stream
set -euo pipefail
ROOT="/mnt/c/Citevision"
ORG="e312f375-7442-4089-8022-ed232abc09e8"
RAW=$(find "$ROOT/data/videos/demo/tmp/$ORG" -name '*_raw.mp4' -size +1M 2>/dev/null | head -1)
if [[ -z "$RAW" ]]; then
  echo "SKIP: no raw demo mp4 found — upload one via /demo first"
  exit 0
fi
VID=$(basename "$RAW" _raw.mp4)
DEST="$ROOT/data/videos/demo/$ORG/${VID}_stream.mp4"
TMP="/tmp/citevision-demo-${VID}_stream.mp4"
echo "Raw: $RAW"
echo "Dest: $DEST"
rm -f "$TMP" "$DEST"
ffmpeg -y -hide_banner -loglevel warning -i "$RAW" \
  -c:v libx264 -preset veryfast -tune zerolatency \
  -bf 0 -g 25 -keyint_min 25 -sc_threshold 0 \
  -r 25 -fps_mode cfr -pix_fmt yuv420p -movflags +faststart -an "$TMP"
SZ=$(stat -c%s "$TMP")
echo "Transcoded: $SZ bytes"
if [[ "$SZ" -lt 4096 ]]; then echo "FAIL: output too small"; exit 1; fi
mkdir -p "$(dirname "$DEST")"
cp "$TMP" "$DEST"
STREAM="demo-${ORG:0:8}-${VID:0:8}"
SRC="ffmpeg:/videos/demo/$ORG/${VID}_stream.mp4#video=copy#loop"
curl -sf -X PUT "http://localhost:1984/api/streams?name=${STREAM}&src=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$SRC'))")"
echo ""
curl -sf "http://localhost:1984/api/streams" | jq -r ".[\"$STREAM\"] | if . then \"OK stream $STREAM registered\" else \"FAIL\" end"
echo "PASS transcode smoke"
