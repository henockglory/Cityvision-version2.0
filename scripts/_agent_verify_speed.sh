#!/usr/bin/env bash
set -uo pipefail
PSQL() { docker exec -i citevision-v2-postgres psql -U citevision -d citevision -tAc "$1"; }
ORG=74d51ead-97a7-4e41-a488-503a9b90c466

echo "=== resolve speed camera (zone Zone_distance_parcourue) ==="
SPEEDCAM=$(PSQL "SELECT camera_id FROM zones WHERE name='Zone_distance_parcourue' LIMIT 1;")
echo "speed camera=$SPEEDCAM"
[ -z "$SPEEDCAM" ] && { echo "no speed camera bound"; exit 2; }

echo "=== switch mono-camera to speed camera ==="
PSQL "UPDATE org_demo_settings SET source_mode='camera', active_camera_id='$SPEEDCAM', active_video_id=NULL, updated_at=NOW() WHERE org_id='$ORG';"

BASE=$(PSQL "SELECT count(*) FROM events WHERE event_type='speeding' AND payload->>'demo'='true';")
echo "baseline speeding events=$BASE"
echo "=== observing 120s for speeding at 30 km/h ==="
for i in $(seq 1 12); do
  sleep 10
  NOW=$(PSQL "SELECT count(*) FROM events WHERE event_type='speeding' AND payload->>'demo'='true';")
  echo "t+$((i*10))s speeding=$NOW (delta=$((NOW-BASE)))"
  if [ "$NOW" -gt "$BASE" ]; then break; fi
done
echo "=== last speeding events (speed/limit/distance) ==="
PSQL "SELECT payload->>'speed_kmh', payload->'metadata'->>'limit', payload->'metadata'->>'distance_m', payload->'metadata'->>'method', occurred_at FROM events WHERE event_type='speeding' AND payload->>'demo'='true' ORDER BY occurred_at DESC LIMIT 5;"
