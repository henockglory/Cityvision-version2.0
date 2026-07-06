#!/usr/bin/env bash
set -uo pipefail
LOGIN=$(curl -sf -X POST http://localhost:8081/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"glory.henock@hologram.cd","password":"Henockglory@03"}')
TOKEN=$(printf '%s' "$LOGIN" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null)
echo "tokenlen=${#TOKEN}"
if [ -z "$TOKEN" ]; then echo "LOGIN_FAILED body:"; echo "$LOGIN" | head -c 300; exit 0; fi
ORG=74d51ead-97a7-4e41-a488-503a9b90c466
CODE=$(curl -s -o /tmp/cat.json -w '%{http_code}' "http://localhost:8081/api/v1/orgs/$ORG/rules/catalog" -H "Authorization: Bearer $TOKEN")
echo "HTTP $CODE  bytes=$(wc -c < /tmp/cat.json)"
head -c 200 /tmp/cat.json; echo
python3 - <<'PY'
import json
try:
    d=json.load(open("/tmp/cat.json"))
except Exception as e:
    print("parse error:",e); raise SystemExit
from collections import Counter
c=Counter((t.get("partial_status") or "full") for t in d)
print("total served:",len(d))
for k,v in sorted(c.items()): print("  %s: %d"%(k,v))
print("not_emitted:", [t["id"] for t in d if t.get("partial_status")=="not_emitted"])
print("partial_status field present:", any("partial_status" in t for t in d))
print("supported count:", sum(1 for t in d if t.get("supported")))
PY
