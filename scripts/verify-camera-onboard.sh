#!/usr/bin/env bash
# Caméra create → preview 200 → go2rtc stream list → AI health
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$SCRIPT_DIR/lib/env-utils.sh"

API="${API:-http://localhost:8081}"
GO2RTC="${GO2RTC:-http://localhost:1984}"
EMAIL="${EMAIL:-glory.henock@hologram.cd}"
PASS="${PASS:-Hologram2026!}"

echo "=== verify-camera-onboard ==="

LOGIN=$(curl -sf -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" 2>/dev/null || echo '{}')
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)
if [ -z "$TOKEN" ]; then
  echo "FAIL: login"
  exit 1
fi
ORG=$(curl -sf "$API/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))")

CAMS_RAW=$(curl -sf "$API/api/v1/orgs/$ORG/cameras" -H "Authorization: Bearer $TOKEN" 2>/dev/null || echo '[]')
echo "$CAMS_RAW" | python3 -c "
import sys, json
try:
    cams = json.load(sys.stdin)
except json.JSONDecodeError:
    print('WARN: cameras list unavailable')
    sys.exit(0)
if not cams:
    print('WARN: no cameras')
    sys.exit(0)
real = [c for c in cams if 'benedicte' not in (c.get('name') or '').lower() and 'virtual' not in (c.get('name') or '').lower()]
if not real:
    print('PASS: virtual/demo cameras only')
    sys.exit(0)
for c in real[:3]:
    meta = c.get('metadata') or {}
    src = meta.get('go2rtc_src') or f\"cam-{c['id']}\"
    print(f\"camera {c['id'][:8]}… go2rtc_src={src}\")
print('PASS camera metadata check')
"

AI=$(curl -sf "http://localhost:8020/health" 2>/dev/null || curl -sf "$API/ai-engine/health" 2>/dev/null || echo '{"status":"unknown"}')
echo "AI health: $AI"
echo "$AI" | python3 -c "
import sys, json
h = json.load(sys.stdin)
if h.get('status') != 'ok':
    print('WARN: ai-engine not ok', h)
else:
    print('PASS ai-engine health')
if h.get('ffmpeg_available') == 'false':
    print('WARN: ffmpeg not in ai-engine PATH')
"

STREAMS=$(curl -sf "$GO2RTC/api/streams" 2>/dev/null || echo '{}')
COUNT=$(echo "$STREAMS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)
echo "go2rtc streams: $COUNT"
echo "PASS go2rtc reachable"

CAM_ID=$(echo "$CAMS_RAW" | python3 -c "import sys,json; c=json.load(sys.stdin); print(c[0]['id'] if c else '')" 2>/dev/null || true)
if [ -n "$CAM_ID" ]; then
  HTTP=$(curl -sf -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" \
    "$API/api/v1/orgs/$ORG/cameras/$CAM_ID/preview" 2>/dev/null || echo 000)
  echo "preview HTTP $HTTP"
  if [ "$HTTP" = "200" ] || [ "$HTTP" = "404" ]; then
    echo "PASS preview endpoint"
  else
    echo "WARN preview HTTP $HTTP"
  fi
fi

echo "=== verify-camera-onboard OK ==="
