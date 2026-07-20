#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
ORG="${DEMO_ORG_ID:-74d51ead-97a7-4e41-a488-503a9b90c466}"

echo "=== demo rules + defs ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -F '|' -c "
SELECT r.name, r.is_enabled, r.id::text,
  left(coalesce(r.definition::text,''), 400)
FROM rules r
WHERE r.org_id='$ORG'::uuid AND r.name LIKE 'Démo%'
ORDER BY r.name;
"

echo
echo "=== lines/zones for counting cam 9a3cd323 ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT 'line' AS kind, id::text, name, left(geometry::text,120) g
FROM lines WHERE camera_id='9a3cd323-3820-46f0-aa5b-86c086a4a782'::uuid
UNION ALL
SELECT 'zone', id::text, name, left(geometry::text,120)
FROM zones WHERE camera_id='9a3cd323-3820-46f0-aa5b-86c086a4a782'::uuid;
"

echo "=== lines/zones for red cam 8ed20433 ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT 'line' AS kind, id::text, name, left(geometry::text,80) g
FROM lines WHERE camera_id='8ed20433-57d5-4999-a6ab-0bea028b23a3'::uuid
UNION ALL
SELECT 'zone', id::text, name, left(geometry::text,80)
FROM zones WHERE camera_id='8ed20433-57d5-4999-a6ab-0bea028b23a3'::uuid;
"

echo "=== event types last 2h ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT event_type, count(*), max(ingested_at) AS last
FROM events
WHERE org_id='$ORG'::uuid AND ingested_at > now() - interval '2 hours'
GROUP BY 1 ORDER BY last DESC;
"

echo "=== AI spatial for counting cam (from /cameras detail if any) ==="
curl -sf http://127.0.0.1:8001/cameras | python3 -c '
import json,sys
d=json.load(sys.stdin)
for c in d.get("cameras") or []:
  cid=c.get("camera_id","")
  if cid.startswith("9a3") or cid.startswith("8ed"):
    print(json.dumps({k:c.get(k) for k in ("camera_id","running","frames_processed","zones","lines","rules","last_error","pipeline")}, default=str)[:500])
'

echo "=== enable counting only + resync + wait 60s sample MQTT/events ==="
# login and enable only counting via SQL for speed (read path)
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
UPDATE rules SET is_enabled=(name='Démo · Comptage véhicules')
WHERE org_id='$ORG'::uuid AND name LIKE 'Démo%';
SELECT name, is_enabled FROM rules WHERE org_id='$ORG'::uuid AND name LIKE 'Démo%';
"
curl -sf -X POST http://127.0.0.1:8010/internal/sync-rules || true
echo
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial; echo
sleep 5
# switch demo video to counting cam video
TOKEN=$(curl -sf -X POST http://127.0.0.1:8081/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"'"${ADMIN_EMAIL:-glory.henock@hologram.cd}"'","password":"'"${ADMIN_PASSWORD:-Hologram2026!}"'"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
curl -sf -X PATCH "http://127.0.0.1:8081/api/v1/orgs/$ORG/demo/settings" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"source_mode":"video","active_video_id":"1a7dd0c0-1557-427c-9a9e-03da850561d9","active_camera_id":null}'; echo
sleep 20
echo "=== events after enable ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT event_type, left(camera_id::text,8), ingested_at
FROM events WHERE org_id='$ORG'::uuid AND ingested_at > now() - interval '3 minutes'
ORDER BY ingested_at DESC LIMIT 20;
"
echo "=== AI log tail counting/line ==="
grep -E 'line_cross|vehicle_count|corridor|count|zone_count|Comptage' /tmp/citevision-ai*.log 2>/dev/null | tail -20 || true
ls /home/gheno/citevision-v2/logs/*ai* 2>/dev/null | tail -5
pgrep -af uvicorn | head -3
