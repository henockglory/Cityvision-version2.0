#!/usr/bin/env bash
# Audit demo spatial: required zones/lines + behavior_config.
set -euo pipefail
FAIL=0

check() {
  local label="$1"
  local sql="$2"
  local n
  n=$(docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c "$sql" 2>/dev/null | tr -d ' \r\n')
  if [[ -z "$n" || "$n" == "0" ]]; then
    echo "[FAIL] $label"
    FAIL=$((FAIL + 1))
  else
    echo "[OK] $label ($n)"
  fi
}

echo "=== Demo spatial audit ==="

echo ""
echo "=== Demo cameras ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT id, name, is_active, metadata->>'demo_video_id' AS video_id FROM cameras WHERE metadata->>'demo' = 'true' ORDER BY name;"

echo ""
echo "=== Zones (demo) ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT z.name, c.name AS camera, z.behavior_config->>'behavior' AS behavior, z.is_active FROM zones z JOIN cameras c ON c.id = z.camera_id WHERE c.metadata->>'demo' = 'true' ORDER BY c.name, z.name;"

echo ""
echo "=== Lines (demo) ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT l.name, c.name AS camera, l.is_active FROM lines l JOIN cameras c ON c.id = l.camera_id WHERE c.metadata->>'demo' = 'true' ORDER BY c.name, l.name;"

echo ""
echo "=== Required entities ==="
check "Zone_des_feux" "SELECT count(*) FROM zones z JOIN cameras c ON c.id=z.camera_id WHERE c.metadata->>'demo'='true' AND z.name='Zone_des_feux';"
check "Zone_Observation" "SELECT count(*) FROM zones z JOIN cameras c ON c.id=z.camera_id WHERE c.metadata->>'demo'='true' AND z.name='Zone_Observation';"
check "Zone_distance_parcourue" "SELECT count(*) FROM zones z JOIN cameras c ON c.id=z.camera_id WHERE c.metadata->>'demo'='true' AND z.name='Zone_distance_parcourue';"
check "Zone_bbox" "SELECT count(*) FROM zones z JOIN cameras c ON c.id=z.camera_id WHERE c.metadata->>'demo'='true' AND z.name='Zone_bbox';"
check "Ligne_count" "SELECT count(*) FROM lines l JOIN cameras c ON c.id=l.camera_id WHERE c.metadata->>'demo'='true' AND l.name='Ligne_count';"

echo ""
echo "=== Required behaviors ==="
check "traffic_light_color on Zone_des_feux" "SELECT count(*) FROM zones z JOIN cameras c ON c.id=z.camera_id WHERE z.name='Zone_des_feux' AND z.behavior_config->>'behavior'='traffic_light_color';"
check "red_light_observation on Zone_Observation" "SELECT count(*) FROM zones z JOIN cameras c ON c.id=z.camera_id WHERE z.name='Zone_Observation' AND z.behavior_config->>'behavior'='red_light_observation';"
check "speed_measurement on Zone_distance_parcourue" "SELECT count(*) FROM zones z JOIN cameras c ON c.id=z.camera_id WHERE z.name='Zone_distance_parcourue' AND z.behavior_config->>'behavior'='speed_measurement';"
check "driver_cabin on Zone_bbox" "SELECT count(*) FROM zones z JOIN cameras c ON c.id=z.camera_id WHERE z.name='Zone_bbox' AND z.behavior_config->>'behavior'='driver_cabin';"

if (( FAIL > 0 )); then
  echo ""
  echo "AUDIT FAILED ($FAIL checks) — run: bash scripts/seed-demo-spatial.sh"
  exit 1
fi
echo ""
echo "AUDIT PASSED"
