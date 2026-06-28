#!/usr/bin/env bash
set -euo pipefail

API="${API_BASE:-http://localhost:8081/api/v1}"
GO2RTC="${GO2RTC_API:-http://localhost:1984/api/streams}"
EMAIL="${DEMO_EMAIL:-glory.henock@hologram.cd}"
PASS="${DEMO_PASS:-Hologram2026!}"

echo "=== Backend health ==="
HEALTH=$(curl -sf "$API/../health/ready" || echo '{"error":"unreachable"}')
echo "$HEALTH"

echo ""
echo "=== go2rtc streams ==="
STREAMS=$(curl -sf "$GO2RTC" || echo '{}')
echo "$STREAMS" | python3 -c "import sys,json; d=json.load(sys.stdin); print('Streams:', list(d.keys()))"

echo ""
echo "=== Login ==="
LOGIN=$(curl -sf -X POST "$API/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" || echo '{"error":"login failed"}')
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))" 2>/dev/null || echo '')
if [ -z "$TOKEN" ]; then
  echo "Login failed: $LOGIN"
  exit 1
fi
echo "OK - got token"

echo ""
echo "=== Demo settings ==="
ORG=$(curl -sf "$API/me" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))")
SETTINGS=$(curl -sf "$API/orgs/$ORG/demo/settings" -H "Authorization: Bearer $TOKEN")
echo "$SETTINGS" | python3 -c "
import sys,json
d=json.load(sys.stdin)
vids=d.get('videos',[])
print('Active video:', d.get('active_video_id'))
print('Active stream:', d.get('active_go2rtc_src'))
print('Video count:', len(vids))
for v in vids:
    print(f'  - {v[\"name\"]} [{v[\"status\"]}] err={v.get(\"error_message\",\"\")}')
"

echo ""
echo "=== DONE ==="
