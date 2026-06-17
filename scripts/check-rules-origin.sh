#!/usr/bin/env bash
set -euo
set -o pipefail

API="${API:-http://localhost:8081}"
EMAIL="${EMAIL:-glory.henock@hologram.cd}"
PASS="${PASS:-Hologram2026!}"

LOGIN=$(curl -sf -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}")
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
ORG=$(curl -sf "$API/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))")

echo "org=$ORG"

curl -sf "$API/api/v1/orgs/$ORG/rules" -H "Authorization: Bearer $TOKEN" \
  | python3 - <<'PY'
import sys, json
rules = json.load(sys.stdin)
total = len(rules)
user = 0
non_user = 0
missing = 0
examples = []
for r in rules:
    bindings = (r.get("definition") or {}).get("bindings") or {}
    origin = bindings.get("origin") if isinstance(bindings, dict) else None
    if origin == "user":
        user += 1
    elif origin is None or origin == "":
        missing += 1
        non_user += 1
        if len(examples) < 5:
            examples.append(r.get("name"))
    else:
        non_user += 1
        if len(examples) < 5:
            examples.append(r.get("name"))
print(f"total_rules={total}")
print(f"user_origin={user}")
print(f"non_user_origin={non_user}")
print(f"missing_origin={missing}")
if examples:
    print("examples_non_user=", examples)
PY

