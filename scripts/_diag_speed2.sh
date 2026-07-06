#!/usr/bin/env bash
set -eu
CAM="01ee632c-271c-4e66-ba98-3d1d7e430c09"
ORG="e312f375-7442-4089-8022-ed232abc09e8"

echo "=== Recent vehicle_corridor speeds ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT payload->>'speed_kmh' as spd, occurred_at FROM events WHERE camera_id='${CAM}' AND event_type='vehicle_corridor' ORDER BY occurred_at DESC LIMIT 10;"

echo ""
echo "=== Last speeding event ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT occurred_at, payload FROM events WHERE camera_id='${CAM}' AND event_type='speeding' ORDER BY occurred_at DESC LIMIT 1;"

echo ""
echo "=== Last alert ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT created_at, message, camera_id, rule_id, metadata FROM alerts WHERE org_id='${ORG}' ORDER BY created_at DESC LIMIT 3;"

echo ""
echo "=== Rules engine status ==="
curl -s http://127.0.0.1:8082/health 2>/dev/null || curl -s http://127.0.0.1:8083/health 2>/dev/null || echo "rules health unknown"

echo ""
echo "=== AI engine cameras ==="
curl -s http://127.0.0.1:8000/cameras 2>/dev/null | head -c 1500 || curl -s http://127.0.0.1:8090/cameras 2>/dev/null | head -c 1500 || echo "ai cameras unknown"
