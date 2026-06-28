#!/usr/bin/env bash
# Test demo video upload end-to-end: upload → poll until ready → check go2rtc.
set -euo pipefail
API="${API_BASE:-http://localhost:8081/api/v1}"
EMAIL="${DEMO_EMAIL:-glory.henock@hologram.cd}"
PASS="${DEMO_PASS:-Hologram2026!}"
ORG="${DEMO_ORG:-e312f375-7442-4089-8022-ed232abc09e8}"
VIDEO="${1:-/mnt/c/Citevision/data/videos/benedicte.mp4}"

echo "==> Login"
TOKEN=$(curl -sf -X POST "$API/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
echo "Token OK: ${TOKEN:0:20}..."

echo "==> Check temp dir writable"
wsl_tmp=$(python3 -c 'import os; print(os.environ.get("VIDEOS_PATH","not set"))')
echo "VIDEOS_PATH: ${VIDEOS_PATH:-not set}"
ls -la "$(dirname "$VIDEO")" | tail -3

echo "==> Upload: $VIDEO"
START=$(date +%s)
RESP=$(curl -sf -X POST "$API/orgs/$ORG/demo/videos" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Org-ID: $ORG" \
  -F "video=@$VIDEO")
echo "Upload response: $RESP"
VID=$(echo "$RESP" | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')
echo "Video ID: $VID"

echo "==> Polling status (max 10 min)..."
for i in $(seq 1 120); do
  ST=$(curl -sf "$API/orgs/$ORG/demo/videos/$VID/status" \
    -H "Authorization: Bearer $TOKEN" -H "X-Org-ID: $ORG")
  STATUS=$(echo "$ST" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["status"])')
  PROGRESS=$(echo "$ST" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["progress"])')
  ELAPSED=$(( $(date +%s) - START ))
  echo "  [${ELAPSED}s] poll $i: $STATUS ($PROGRESS%)"
  if [[ "$STATUS" == "ready" ]]; then
    echo "OK: video ready in ${ELAPSED}s"
    break
  fi
  if [[ "$STATUS" == "failed" ]]; then
    echo "$ST" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("error_message","?"))'
    echo "FAIL: transcode failed"
    exit 1
  fi
  sleep 5
done

echo "==> Check go2rtc stream"
SETTINGS=$(curl -sf "$API/orgs/$ORG/demo/settings" -H "Authorization: Bearer $TOKEN" -H "X-Org-ID: $ORG")
STREAM=$(echo "$SETTINGS" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("active_go2rtc_src",""))')
echo "Active stream: $STREAM"
if curl -sf http://localhost:1984/api/streams | python3 -c "import json,sys; d=json.load(sys.stdin); assert '$STREAM' in d" 2>/dev/null; then
  echo "OK: stream in go2rtc"
else
  echo "WARN: stream not in go2rtc"
fi

echo "==> Check stream file visible to go2rtc Docker"
docker exec citevision-v2-go2rtc ls -lah /videos/demo/ 2>/dev/null || echo "WARN: docker ls failed"

echo "PASS: test-upload-demo"
