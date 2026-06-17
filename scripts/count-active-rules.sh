#!/usr/bin/env bash
set -euo pipefail
API="${API:-http://localhost:8081}"
TOKEN=$(curl -sf "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d '{"email":"glory.henock@hologram.cd","password":"Hologram2026!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
ORG=$(curl -sf "$API/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['org_id'])")
ENABLED=$(curl -sf "$API/api/v1/orgs/$ORG/rules" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; print(sum(1 for r in json.load(sys.stdin) if r.get('is_enabled')))")
echo "Enabled rules in DB: $ENABLED"
