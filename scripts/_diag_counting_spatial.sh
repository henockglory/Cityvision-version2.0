#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
ORG=74d51ead-97a7-4e41-a488-503a9b90c466
CAM=9a3cd323-3820-46f0-aa5b-86c086a4a782

echo "=== line geometry ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT name, is_active, start_point, end_point, behavior_config, direction
FROM lines WHERE camera_id='$CAM'::uuid;
"

echo "=== zones on counting cam ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT name, is_active, behavior_config, left(points::text,120)
FROM zones WHERE camera_id='$CAM'::uuid;
" 2>&1 | head -40

TOKEN=$(curl -sf -X POST http://127.0.0.1:8081/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"'"${ADMIN_EMAIL:-glory.henock@hologram.cd}"'","password":"'"${ADMIN_PASSWORD:-Hologram2026!}"'"}' \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')

echo "=== API lines ==="
curl -sf "http://127.0.0.1:8081/api/v1/orgs/$ORG/lines?camera_id=$CAM" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -60

echo "=== force resync and peek AI debug if any ==="
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial; echo
sleep 3

# Try common debug endpoints
for path in \
  "/debug/spatial/$CAM" \
  "/cameras/$CAM/spatial" \
  "/internal/spatial/$CAM" \
  "/spatial/$CAM"
do
  code=$(curl -sf -o /tmp/ai_sp.json -w '%{http_code}' "http://127.0.0.1:8001$path" || echo 000)
  echo "AI $path -> $code"
  [[ "$code" == "200" ]] && head -c 800 /tmp/ai_sp.json && echo
done

echo "=== AI log for line/spatial (recent) ==="
# find ai log
for f in /tmp/citevision-ai.log /home/gheno/citevision-v2/logs/ai-engine.log /home/gheno/citevision-v2/logs/uvicorn*.log; do
  [[ -f "$f" ]] && echo "log=$f" && grep -E 'line_cross|Ligne_count|spatial|lines=' "$f" | tail -20
done
journalctl --user -u citevision-ai --no-pager -n 5 2>/dev/null | head -5 || true

# Check MQTT recent line_cross
echo "=== mosquitto? ==="
docker logs --tail 5 citevision-v2-mosquitto 2>&1 | tail -5

echo "=== sample detections from AI health/metrics ==="
curl -sf http://127.0.0.1:8001/health | python3 -m json.tool | head -40
