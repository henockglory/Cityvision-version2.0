#!/usr/bin/env bash
set -uo pipefail
ROOT=~/citevision-v2
cd "$ROOT"
CAM=8ed20433-57d5-4999-a6ab-0bea028b23a3
ORG=74d51ead-97a7-4e41-a488-503a9b90c466

docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT z.name, z.behavior, jsonb_array_length(COALESCE(z.polygon,'[]'::jsonb)) AS pts,
       left(z.behavior_config::text,120) AS cfg
FROM zones z
WHERE z.camera_id = '$CAM'
ORDER BY z.behavior, z.name;
"

echo "=== rules ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT name, is_enabled, event_type, camera_ids
FROM rules
WHERE org_id='$ORG' AND (name ILIKE '%feu%' OR event_type ILIKE '%red_light%' OR definition::text ILIKE '%red_light%')
ORDER BY name;
"

echo "=== recent events ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT event_type, created_at, camera_id::text
FROM events
WHERE camera_id='$CAM' AND created_at > now() - interval '2 hours'
ORDER BY created_at DESC LIMIT 15;
"

echo "=== MQTT / publish sample from AI log ==="
grep -E 'traffic_light|red_light|publish_event|mqtt' "$ROOT/logs/ai-engine.log" | tail -30 || true

echo "=== spatial config push ==="
grep -E 'spatial|hot-reload|zones_cfg|8ed20433' "$ROOT/logs/backend.log" | tail -20 || true
