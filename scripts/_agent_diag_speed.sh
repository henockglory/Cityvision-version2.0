#!/usr/bin/env bash
set -uo pipefail
L=/home/gheno/citevision-v2/logs/ai-engine.log
SPEEDCAM=55694d53-8f58-4981-91b2-7c6cd528a25d
echo "=== ingest/camera activity for speed cam ==="
tail -600 "$L" | grep -iE "$SPEEDCAM|Ligne Continue|ingest|processing camera" | tail -20
echo "=== zone_speed / speeding / spatial reload ==="
tail -800 "$L" | grep -iE "zone_speed|speeding|speed_measurement|spatial config|behaviors|Zone_distance" | tail -30
echo "=== errors ==="
tail -300 "$L" | grep -iE "error|traceback|exception|failed" | tail -12
echo "=== spatial config in DB for speed cam zone ==="
docker exec -i citevision-v2-postgres psql -U citevision -d citevision -tAc "SELECT name, camera_id, behavior_config FROM zones WHERE name='Zone_distance_parcourue';"
