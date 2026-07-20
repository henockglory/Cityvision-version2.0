#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
ORG=74d51ead-97a7-4e41-a488-503a9b90c466
CAM=9a3cd323-3820-46f0-aa5b-86c086a4a782

echo "=== ensure counting video + rule + spatial ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
UPDATE rules SET is_enabled=(name='Démo · Comptage véhicules')
WHERE org_id='$ORG'::uuid AND name LIKE 'Démo%';
"
TOKEN=$(curl -sf -X POST http://127.0.0.1:8081/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"'"${ADMIN_EMAIL:-glory.henock@hologram.cd}"'","password":"'"${ADMIN_PASSWORD:-Hologram2026!}"'"}' \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')

curl -sf -X PATCH "http://127.0.0.1:8081/api/v1/orgs/$ORG/demo/settings" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"source_mode":"video","active_video_id":"1a7dd0c0-1557-427c-9a9e-03da850561d9","active_camera_id":null}'; echo

curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial; echo
curl -sf -X POST http://127.0.0.1:8010/internal/sync-rules; echo

echo "=== wait ingest ready ==="
for i in $(seq 1 30); do
  st=$(curl -sf "http://127.0.0.1:8081/api/v1/orgs/$ORG/demo/settings" -H "Authorization: Bearer $TOKEN" \
    | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("pipeline_status"), d.get("ingest_ready"), d.get("active_camera_id","")[:8])')
  echo "  $i $st"
  echo "$st" | grep -q 'True' && break
  sleep 3
done

echo "=== AI camera spatial (internal if any) ==="
curl -sf "http://127.0.0.1:8001/cameras/$CAM" | python3 -m json.tool 2>/dev/null | head -80 || \
curl -sf "http://127.0.0.1:8001/cameras" | python3 -c '
import json,sys
d=json.load(sys.stdin)
for c in d.get("cameras") or []:
  if c.get("camera_id","").startswith("9a3"):
    print(json.dumps(c, indent=2)[:2000])
'

echo "=== backend spatial for cam ==="
curl -sf "http://127.0.0.1:8081/api/v1/orgs/$ORG/cameras/$CAM/spatial" \
  -H "Authorization: Bearer $TOKEN" | python3 -c '
import json,sys
d=json.load(sys.stdin)
print("keys", list(d.keys()) if isinstance(d,dict) else type(d))
if isinstance(d,dict):
  lines=d.get("lines") or d.get("Lines") or []
  zones=d.get("zones") or d.get("Zones") or []
  print("lines", len(lines), "zones", len(zones))
  for L in lines[:5]:
    print(" LINE", L.get("name"), L.get("is_active"), L.get("start_point") or L.get("start"), L.get("end_point") or L.get("end"))
  for Z in zones[:5]:
    print(" ZONE", Z.get("name"), Z.get("behavior") or (Z.get("behavior_config") or {}).get("behavior"))
' 2>&1 | head -40

echo "=== baseline counter + wait 90s for line_cross ==="
BEFORE=$(docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT count_total FROM line_counters WHERE camera_id='$CAM'::uuid AND line_id='Ligne_count' AND class_filter='car' LIMIT 1;")
echo "counter_before=$BEFORE"
SINCE=$(date -u +'%Y-%m-%d %H:%M:%S+00')
sleep 90
AFTER=$(docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT count_total FROM line_counters WHERE camera_id='$CAM'::uuid AND line_id='Ligne_count' AND class_filter='car' LIMIT 1;")
EV=$(docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT count(*) FROM events WHERE camera_id='$CAM'::uuid AND event_type='line_cross' AND ingested_at>='$SINCE'::timestamptz;")
echo "counter_after=$AFTER events_since=$EV since=$SINCE"

echo "=== AI frames ==="
curl -sf http://127.0.0.1:8001/cameras | python3 -c '
import json,sys
d=json.load(sys.stdin)
for c in d.get("cameras") or []:
  print(c.get("camera_id"), c.get("frames_processed"), c.get("running"), c.get("last_error"))
'
