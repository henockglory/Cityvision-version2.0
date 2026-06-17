#!/usr/bin/env bash
# Reset commercial: désactive toutes les règles + purge alertes/événements/évidences (DB + MinIO)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$SCRIPT_DIR/lib/env-utils.sh"

API="${API:-http://localhost:8081}"
EMAIL="${EMAIL:-glory.henock@hologram.cd}"
PASS="${PASS:-Hologram2026!}"

echo "=== reset-commercial (rules off + purge evidence) ==="

LOGDIR="$SCRIPT_DIR/../logs"
stop_from_pid "$LOGDIR/ai-engine.pid" 2>/dev/null || true
sleep 2

LOGIN=$(curl -sf -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}")
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
ORG=$(curl -sf "$API/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))")

if [ -z "$TOKEN" ] || [ -z "$ORG" ]; then
  echo "FAIL: login"
  exit 1
fi

RESULT=$(curl -sf -X POST "$API/api/v1/orgs/$ORG/maintenance/purge" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")
echo "$RESULT" | python3 -m json.tool

echo "$RESULT" | python3 -c "
import sys, json
r = json.load(sys.stdin)
assert r.get('status') == 'purged', r
print('PASS rules_disabled=', r.get('rules_disabled', 0))
print('PASS alerts_deleted=', r.get('alerts_deleted', 0))
print('PASS events_deleted=', r.get('events_deleted', 0))
print('PASS evidence_objects_deleted=', r.get('evidence_objects_deleted', 0))
"

ACTIVE=$(curl -sf "$API/api/v1/orgs/$ORG/rules" -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys,json
rules=json.load(sys.stdin) or []
print(sum(1 for r in rules if r.get('is_enabled')))
")
if [ "$ACTIVE" != "0" ]; then
  echo "FAIL: still $ACTIVE active rules"
  exit 1
fi
echo "PASS active_rules=0"

count_json_list() {
  python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 0)"
}

ALERTS=$(curl -sf "$API/api/v1/orgs/$ORG/alerts?limit=5" -H "Authorization: Bearer $TOKEN" | count_json_list)
EVENTS=$(curl -sf "$API/api/v1/orgs/$ORG/events?limit=5" -H "Authorization: Bearer $TOKEN" | count_json_list)
echo "alerts_remaining=$ALERTS events_remaining=$EVENTS"

if [ "$ALERTS" != "0" ] || [ "$EVENTS" != "0" ]; then
  echo "INFO: residual rows detected — second purge pass"
  RESULT2=$(curl -sf -X POST "$API/api/v1/orgs/$ORG/maintenance/purge" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json")
  echo "$RESULT2" | python3 -m json.tool
  sleep 2
  ALERTS=$(curl -sf "$API/api/v1/orgs/$ORG/alerts?limit=5" -H "Authorization: Bearer $TOKEN" | count_json_list)
  EVENTS=$(curl -sf "$API/api/v1/orgs/$ORG/events?limit=5" -H "Authorization: Bearer $TOKEN" | count_json_list)
  echo "alerts_remaining=$ALERTS events_remaining=$EVENTS"
fi

bash "$SCRIPT_DIR/restart-ai-engine.sh" >/dev/null 2>&1 || true

echo "=== reset-commercial OK ==="
