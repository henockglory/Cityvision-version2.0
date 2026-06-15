#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_URL="${API_URL:-http://localhost:8081}"

echo "==> Seeding test zones, lines, and rules for virtual camera"

TOKEN=$(curl -sf "$API_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"'"${ADMIN_EMAIL:-glory.henock@hologram.cd}"'","password":"'"${ADMIN_PASSWORD:-Hologram2026!}"'"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)

if [ -z "$TOKEN" ]; then
  echo "Login failed â€” run setup first or set ADMIN_EMAIL/ADMIN_PASSWORD"
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
  -d "$ZONE_JSON" | python3 -m json.tool

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
  -d "$LINE_JSON" | python3 -m json.tool

RULES=(
  '{"name":"Intrusion test-zone","definition":{"condition":{"op":"AND","children":[{"op":"eq","field":"event","value":"zone_enter"},{"op":"in_zone","field":"zone_id","value":"test-zone"}]},"actions":[{"type":"alert","config":{"severity":"high"}}]},"priority":10}'
  '{"name":"Line cross entry","definition":{"condition":{"op":"eq","field":"event","value":"line_cross"},"actions":[{"type":"alert","config":{"severity":"medium"}}]},"priority":20}'
  '{"name":"Loitering alert","definition":{"condition":{"op":"eq","field":"event","value":"loitering"},"actions":[{"type":"alert","config":{"severity":"warning"}}]},"priority":30}'
  '{"name":"Crowd gathering","definition":{"condition":{"op":"eq","field":"event","value":"crowd_gathering"},"actions":[{"type":"alert","config":{"severity":"medium"}}]},"priority":40}'
  '{"name":"Running detected","definition":{"condition":{"op":"eq","field":"event","value":"running"},"actions":[{"type":"alert","config":{"severity":"medium"}}]},"priority":50}'
  '{"name":"Face detected","definition":{"condition":{"op":"eq","field":"event","value":"face_detected"},"actions":[{"type":"alert","config":{"severity":"info"}}]},"priority":60}'
  '{"name":"Plate detected","definition":{"condition":{"op":"eq","field":"event","value":"plate_detected"},"actions":[{"type":"alert","config":{"severity":"info"}}]},"priority":70}'
  '{"name":"Video blur","definition":{"condition":{"op":"eq","field":"event","value":"video_blur"},"actions":[{"type":"alert","config":{"severity":"info"}}]},"priority":80}'
)

for rule in "${RULES[@]}"; do
  curl -sf -X POST "$API_URL/api/v1/orgs/$ORG_ID/rules" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$rule" >/dev/null && echo "[OK] Rule created"
done

echo "==> Spatial config seeded. Orchestrator will reload within 10s."
