#!/usr/bin/env bash
# Purge alertes/événements/MinIO, redémarre les services, lance E2E zone+alerte avec preuves complètes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR/.."
cd "$ROOT"
# shellcheck source=scripts/lib/env-utils.sh
source "$SCRIPT_DIR/lib/env-utils.sh"

API="${API:-http://localhost:8081}"

echo "=== reset-evidence-fresh ==="

echo ">>> Step 1: commercial purge (rules off, alerts/events/evidence cleared)"
bash "$SCRIPT_DIR/reset-commercial.sh"

echo ">>> Step 2: restart API + frontend"
bash "$SCRIPT_DIR/restart-api-frontend.sh"

echo ">>> Step 3: E2E zone presence rule + evidence capture (CLEANUP=0)"
if ! wait_http_ok "${API:-http://localhost:8081}/health" 30; then
  echo "FAIL: backend not reachable before E2E"
  exit 1
fi
CLEANUP=0 bash "$SCRIPT_DIR/verify-e2e-zone-alert.sh"

echo ">>> Step 4: evidence playback check"
bash "$SCRIPT_DIR/verify-evidence-playback.sh"

EMAIL="${EMAIL:-glory.henock@hologram.cd}"
PASS="${PASS:-Hologram2026!}"
LOGIN=$(curl -sf -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}")
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
ORG=$(curl -sf "$API/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))")

echo ">>> Step 5: summary counts"
ALERTS=$(curl -sf "$API/api/v1/orgs/$ORG/alerts?limit=50" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
EVENTS=$(curl -sf "$API/api/v1/orgs/$ORG/events?limit=50&rule_linked=true" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
ACTIVE=$(curl -sf "$API/api/v1/orgs/$ORG/rules" -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys,json
rules=json.load(sys.stdin) or []
print(sum(1 for r in rules if r.get('is_enabled')))
")

echo "alerts=$ALERTS events_rule_linked=$EVENTS active_rules=$ACTIVE"

if [ "${ALERTS:-0}" -lt 1 ]; then
  echo "FAIL: expected at least 1 alert after E2E"
  exit 1
fi
if [ "${EVENTS:-0}" -lt 1 ]; then
  echo "FAIL: expected at least 1 rule-linked event after E2E"
  exit 1
fi
if [ "${ACTIVE:-0}" -lt 1 ]; then
  echo "FAIL: expected at least 1 active rule after E2E"
  exit 1
fi

echo ""
echo "=== reset-evidence-fresh OK ==="
echo "UI: http://localhost:5174/alerts and http://localhost:5174/events"
echo "Verify: select an alert — Preuves clip should play without 'Impossible de charger ce média'"
