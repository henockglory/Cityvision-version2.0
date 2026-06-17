#!/usr/bin/env bash
# Crée une règle de routage, dry-run test, vérifie match
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$SCRIPT_DIR/lib/env-utils.sh"

API="${API:-http://localhost:8081}"
EMAIL="${EMAIL:-glory.henock@hologram.cd}"
PASS="${PASS:-Hologram2026!}"
CLEANUP="${CLEANUP:-1}"

echo "=== verify-routing-rules ==="

LOGIN=$(curl -sf -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}")
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
ORG=$(curl -sf "$API/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))")

RULE_RESP=$(curl -sf -X POST "$API/api/v1/orgs/$ORG/routing-rules" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"E2E plate test","priority":50,"match":{"type":"plate","value":"E2E-999"},"channels":{"emails":["test@example.com"]}}')
RULE_ID=$(echo "$RULE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "created routing rule=$RULE_ID"

TEST=$(curl -sf -X POST "$API/api/v1/orgs/$ORG/routing-rules/test" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"plate_number":"E2E-999","severity":"medium"}')
COUNT=$(echo "$TEST" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count',0))")
if [ "$COUNT" -lt 1 ]; then
  echo "FAIL: dry-run expected >=1 match, got $COUNT"
  exit 1
fi
echo "PASS dry-run matched $COUNT rule(s)"

TEST_NEG=$(curl -sf -X POST "$API/api/v1/orgs/$ORG/routing-rules/test" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"plate_number":"NO-MATCH-XYZ"}')
COUNT_NEG=$(echo "$TEST_NEG" | python3 -c "
import sys, json
items = json.load(sys.stdin).get('matched') or []
print(len([m for m in items if (m.get('match') or {}).get('value') == 'E2E-999']))
")
if [ "$COUNT_NEG" -ne 0 ]; then
  echo "FAIL: plate NO-MATCH-XYZ should not match E2E-999 rule (got $COUNT_NEG)"
  exit 1
fi
echo "PASS non-matching plate excluded"

if [ "$CLEANUP" = "1" ]; then
  curl -sf -X DELETE "$API/api/v1/orgs/$ORG/routing-rules/$RULE_ID" -H "Authorization: Bearer $TOKEN" >/dev/null || true
  echo "cleanup: routing rule deleted"
fi

echo "=== verify-routing-rules OK ==="
