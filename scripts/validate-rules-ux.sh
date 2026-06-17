#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API="${API:-http://localhost:8081}"
EMAIL="${EMAIL:-glory.henock@hologram.cd}"
PASS="${PASS:-Hologram2026!}"

echo "=== validate-rules-ux (seed + activation toggle test) ==="

echo ">>> reset-commercial"
bash "$ROOT/scripts/reset-commercial.sh"

echo ">>> seed-test-spatial (system-origin rules, hidden from Mes règles)"
ADMIN_EMAIL="${ADMIN_EMAIL:-$EMAIL}" ADMIN_PASSWORD="${ADMIN_PASSWORD:-$PASS}" bash "$ROOT/scripts/seed-test-spatial.sh"

LOGIN=$(curl -sf -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}")
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
ORG=$(curl -sf "$API/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))")

echo ">>> create one user-origin rule for UI toggle test"
TEST_RULE_ID=$(python3 - "$API" "$TOKEN" "$ORG" <<'PY'
import json, sys, urllib.request
api, token, org = sys.argv[1:4]
body = {
    "name": "UX toggle test",
    "priority": 5,
    "definition": {
        "bindings": {
            "template_id": "tpl-intrusion-zone",
            "origin": "user",
            "class_filter": "person",
        },
        "condition": {"op": "eq", "field": "event_type", "value": "zone_enter"},
        "actions": [{"type": "alert", "config": {"severity": "medium"}}],
    },
}
req = urllib.request.Request(
    f"{api}/api/v1/orgs/{org}/rules",
    data=json.dumps(body).encode(),
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req) as resp:
    r = json.loads(resp.read().decode())
    rid = r.get("id", "")
    if rid:
        body = json.dumps({"is_enabled": False}).encode()
        req2 = urllib.request.Request(
            f"{api}/api/v1/orgs/{org}/rules/{rid}",
            data=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="PATCH",
        )
        urllib.request.urlopen(req2).read()
    print(rid)
PY
)
export TEST_RULE_ID
echo "TEST_RULE_ID=$TEST_RULE_ID"

echo ">>> ensure playwright"
npm --prefix "$ROOT/frontend" install -D @playwright/test >/dev/null 2>&1 || true
npx --prefix "$ROOT/frontend" playwright install chromium >/dev/null 2>&1 || true

echo ">>> run spec"
cd "$ROOT/frontend"
FRONTEND="${FRONTEND:-http://localhost:5174}" EMAIL="$EMAIL" PASS="$PASS" TEST_RULE_ID="$TEST_RULE_ID" npx playwright test e2e/rules-activation.spec.ts

echo "=== validate-rules-ux OK ==="

