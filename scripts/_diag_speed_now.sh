#!/usr/bin/env bash
set -eu
CAM="01ee632c-271c-4e66-ba98-3d1d7e430c09"
ORG="e312f375-7442-4089-8022-ed232abc09e8"

echo "=== Zone config ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT name, zone_kind, behavior_config FROM zones WHERE camera_id='${CAM}';"

echo ""
echo "=== Events last 10 min ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT event_type, count(*) FROM events WHERE camera_id='${CAM}' AND occurred_at > now() - interval '10 minutes' GROUP BY 1 ORDER BY 2 DESC LIMIT 15;"

echo ""
echo "=== Speeding total ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT count(*), max(occurred_at) FROM events WHERE camera_id='${CAM}' AND event_type='speeding';"

echo ""
echo "=== Alerts last hour ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT count(*), max(created_at) FROM alerts WHERE org_id='${ORG}' AND created_at > now() - interval '1 hour';"

echo ""
echo "=== AI spatial for camera ==="
curl -s "http://127.0.0.1:8081/internal/cameras/${CAM}/config" 2>/dev/null | head -c 2000 || echo "curl failed"

echo ""
echo "=== AI health ==="
curl -s "http://127.0.0.1:8090/health" 2>/dev/null || echo "ai health failed"
