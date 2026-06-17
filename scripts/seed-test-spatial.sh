#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_URL="${API_URL:-http://localhost:8081}"

echo "==> Seeding test zones, lines, and 3 rules (modern format + evidence policy)"

TOKEN=$(curl -sf "$API_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"'"${ADMIN_EMAIL:-glory.henock@hologram.cd}"'","password":"'"${ADMIN_PASSWORD:-Hologram2026!}"'"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)

if [ -z "$TOKEN" ]; then
  echo "Login failed — run setup first or set ADMIN_EMAIL/ADMIN_PASSWORD"
  exit 1
fi

ORG_ID=$(curl -sf "$API_URL/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))")

CAM_JSON=$(curl -sf "$API_URL/api/v1/orgs/$ORG_ID/cameras" -H "Authorization: Bearer $TOKEN")
read -r CAMERA_ID SITE_ID <<< "$(echo "$CAM_JSON" | python3 -c "
import sys, json
cams = json.load(sys.stdin)
cam = next((c for c in cams if 'virtual' in c.get('name','').lower() or c.get('metadata',{}).get('virtual')), cams[0] if cams else None)
if not cam:
    sys.exit(1)
print(cam['id'], cam['site_id'])
")"

echo "Camera: $CAMERA_ID  Site: $SITE_ID"

EVIDENCE='{"enabled":true,"clip_seconds":6,"draw_bbox":true,"images":[{"role":"scene","label":"Vue d'\''ensemble","crop":"full"},{"role":"subject","label":"Cible détectée","crop":"bbox","padding_pct":10,"zoom":1.0}],"min_confidence":0}'

ZONE_JSON='{
  "site_id": "'"$SITE_ID"'",
  "camera_id": "'"$CAMERA_ID"'",
  "name": "test-zone",
  "polygon": [
    {"x": 0.15, "y": 0.2},
    {"x": 0.85, "y": 0.2},
    {"x": 0.85, "y": 0.85},
    {"x": 0.15, "y": 0.85}
  ],
  "color": "#00ffff"
}'

curl -sf -X POST "$API_URL/api/v1/orgs/$ORG_ID/zones" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$ZONE_JSON" >/dev/null 2>&1 || true

LINE_JSON='{
  "site_id": "'"$SITE_ID"'",
  "camera_id": "'"$CAMERA_ID"'",
  "name": "entry-line",
  "start_point": {"x": 0.1, "y": 0.5},
  "end_point": {"x": 0.9, "y": 0.5},
  "direction": "both"
}'

curl -sf -X POST "$API_URL/api/v1/orgs/$ORG_ID/lines" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$LINE_JSON" >/dev/null 2>&1 || true

python3 - "$API_URL" "$TOKEN" "$ORG_ID" "$CAMERA_ID" "$EVIDENCE" <<'PY'
import json, sys, urllib.request

api, token, org, camera_id, evidence_raw = sys.argv[1:6]
evidence = json.loads(evidence_raw)

rules = [
    {
        "name": "Intrusion test-zone",
        "priority": 10,
        "definition": {
            "bindings": {
                "template_id": "tpl-intrusion-zone",
                "camera_id": camera_id,
                "zone_name": "test-zone",
                "class_filter": "person",
                "origin": "system",
            },
            "condition": {
                "op": "AND",
                "children": [
                    {"op": "eq", "field": "event_type", "value": "zone_enter"},
                    {"op": "eq", "field": "zone_id", "value": "test-zone"},
                    {"op": "matches_class", "value": "person"},
                ],
            },
            "actions": [{"type": "alert", "config": {"severity": "high"}}],
            "evidence": evidence,
        },
    },
    {
        "name": "Line cross entry",
        "priority": 20,
        "definition": {
            "bindings": {
                "template_id": "tpl-line-cross",
                "camera_id": camera_id,
                "line_name": "entry-line",
                "class_filter": "person",
                "origin": "system",
            },
            "condition": {
                "op": "AND",
                "children": [
                    {"op": "eq", "field": "event_type", "value": "line_cross"},
                    {"op": "matches_class", "value": "person"},
                ],
            },
            "actions": [{"type": "alert", "config": {"severity": "medium"}}],
            "evidence": evidence,
        },
    },
    {
        "name": "Présence zone test",
        "priority": 30,
        "definition": {
            "bindings": {
                "template_id": "tpl-zone-presence",
                "camera_id": camera_id,
                "zone_name": "test-zone",
                "class_filter": "person",
                "origin": "system",
            },
            "condition": {
                "op": "AND",
                "children": [
                    {"op": "eq", "field": "event_type", "value": "zone_presence"},
                    {"op": "eq", "field": "zone_id", "value": "test-zone"},
                    {"op": "matches_class", "value": "person"},
                ],
            },
            "actions": [{"type": "alert", "config": {"severity": "medium"}}],
            "evidence": evidence,
        },
    },
]

for rule in rules:
    body = json.dumps(rule).encode()
    req = urllib.request.Request(
        f"{api}/api/v1/orgs/{org}/rules",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            resp.read()
        print(f"[OK] Rule created: {rule['name']}")
    except Exception as e:
        print(f"[skip] {rule['name']}: {e}")
PY

echo "==> 3 spatial test rules seeded. Run scripts/trim-test-rules.sh to disable extras."
