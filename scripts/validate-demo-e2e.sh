#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="${API_URL:-http://localhost:8081}"
EMAIL="${DEMO_EMAIL:-glory.henock@hologram.cd}"
PASS="${DEMO_PASS:-Hologram2026!}"
MIN_EVENTS="${MIN_EVENTS:-1}"

echo "==> Demo E2E API validation"
sleep 5

HEALTH=$(curl -sf "$API/health" || echo '{}')
echo "$HEALTH" | python3 -m json.tool 2>/dev/null || true

AI=$(curl -sf http://localhost:8001/health || echo '{}')
YOLO=$(echo "$AI" | python3 -c "import sys,json; print(json.load(sys.stdin).get('yolo_loaded','false'))" 2>/dev/null || echo false)
[[ "$YOLO" == "true" ]] || { echo "[FAIL] yolo_loaded false"; exit 1; }

TOKEN=$(curl -sf "$API/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

ORG=$(curl -sf "$API/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['org_id'])")

CAMS=$(curl -sf "$API/api/v1/orgs/$ORG/cameras" -H "Authorization: Bearer $TOKEN")
CAM_COUNT=$(echo "$CAMS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 0)")
echo "Cameras: $CAM_COUNT"
[[ "$CAM_COUNT" -ge 1 ]] || { echo "[FAIL] no camera"; exit 1; }

VIRTUAL_COUNT=$(echo "$CAMS" | python3 -c "
import sys,json
cams=json.load(sys.stdin)
print(sum(1 for c in cams if 'benedicte' in c.get('name','').lower() or (c.get('metadata') or {}).get('virtual')))
")
[[ "$VIRTUAL_COUNT" -le 1 ]] || { echo "[FAIL] duplicate virtual cameras: $VIRTUAL_COUNT"; exit 1; }

CATALOG=$(curl -sf "$API/api/v1/orgs/$ORG/rules/catalog" -H "Authorization: Bearer $TOKEN")
CAT_LEN=$(echo "$CATALOG" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 0)")
echo "Catalog templates: $CAT_LEN"
[[ "$CAT_LEN" -ge 5 ]] || { echo "[FAIL] catalog too small"; exit 1; }

ZONES=$(curl -sf "$API/api/v1/orgs/$ORG/zones" -H "Authorization: Bearer $TOKEN")
echo "Zones: $(echo "$ZONES" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 0)')"

RULES=$(curl -sf "$API/api/v1/orgs/$ORG/rules" -H "Authorization: Bearer $TOKEN")
RULE_COUNT=$(echo "$RULES" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 0)")
echo "Rules: $RULE_COUNT"

EVENTS=$(curl -sf "$API/api/v1/orgs/$ORG/events?limit=10" -H "Authorization: Bearer $TOKEN")
EVENT_COUNT=$(echo "$EVENTS" | python3 -c "import sys,json; d=json.load(sys.stdin); d=d if isinstance(d,list) else []; print(len(d))")
echo "Events: $EVENT_COUNT"

ALERTS=$(curl -sf "$API/api/v1/orgs/$ORG/alerts?limit=10" -H "Authorization: Bearer $TOKEN")
ALERT_COUNT=$(echo "$ALERTS" | python3 -c "import sys,json; d=json.load(sys.stdin); d=d if isinstance(d,list) else []; print(len(d))")
echo "Alerts: $ALERT_COUNT"

if [[ "$EVENT_COUNT" -lt "$MIN_EVENTS" ]]; then
  echo "[WARN] events < $MIN_EVENTS — wait for video pipeline or lower MIN_EVENTS"
fi

echo "[OK] Demo E2E API validation passed"
