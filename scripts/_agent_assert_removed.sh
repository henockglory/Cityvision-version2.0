#!/usr/bin/env bash
set -uo pipefail
TOKEN=$(curl -sf -X POST http://localhost:8081/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"glory.henock@hologram.cd","password":"Henockglory@03"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin).get("access_token",""))')
ORG=74d51ead-97a7-4e41-a488-503a9b90c466
curl -sf "http://localhost:8081/api/v1/orgs/$ORG/rules/catalog" -H "Authorization: Bearer $TOKEN" > /tmp/cat.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/cat.json"))
ids={t["id"] for t in d}
removed=["tpl-erratic-motion","tpl-behavior-anomaly","tpl-vandalism","tpl-scene-occupancy","tpl-bottleneck","tpl-flow-rate","tpl-zone-occupancy","tpl-face-count","tpl-face-repeat","tpl-running","tpl-wandering","tpl-falling","tpl-crouch-detected","tpl-climb-detected","tpl-carry-object","tpl-fighting","tpl-queue-forming","tpl-tailgating","tpl-wrong-way","tpl-crowd-gathering","tpl-accident"]
still=[r for r in removed if r in ids]
print("total served:", len(d))
print("still present (should be empty):", still)
demo=["tpl-red-light","tpl-line-cross-bidir","tpl-speeding-premium","tpl-phone-driving","tpl-seatbelt"]
print("demo present:", [x for x in demo if x in ids], "/ 5")
PY
