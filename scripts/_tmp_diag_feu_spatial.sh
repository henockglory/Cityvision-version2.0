#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
CAM=8ed20433-57d5-4999-a6ab-0bea028b23a3
ORG=74d51ead-97a7-4e41-a488-503a9b90c466

echo "=== debug spatial ==="
curl -sf -H "X-Internal-Key: $KEY" \
  "http://127.0.0.1:8081/api/v1/internal/ingest/debug-spatial/$CAM" | python3 -m json.tool 2>/dev/null | head -80 || \
curl -sf -H "X-Internal-Key: $KEY" \
  "http://127.0.0.1:8081/api/v1/internal/cameras/$CAM/spatial" | head -c 1500 || echo "no debug endpoint"

echo
echo "=== DB events last 30m ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT event_type, occurred_at
FROM events
WHERE camera_id='$CAM' AND occurred_at > now() - interval '30 minutes'
ORDER BY occurred_at DESC LIMIT 15;
"

echo "=== rules feu ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT name, is_enabled, left(definition::text,180)
FROM rules WHERE org_id='$ORG' AND name ILIKE '%feu%';
"

echo "=== AI log any traffic ==="
grep -iE 'traffic|red_light|Zone_des_feux|8ed20433' "$ROOT/logs/ai-engine.log" | tail -20 || true
