#!/usr/bin/env bash
set -euo pipefail
CAM=01ee632c-271c-4e66-ba98-3d1d7e430c09
ORG=e312f375-7442-4089-8022-ed232abc09e8
PAYLOAD=$(cat <<EOF
{"event_type":"speeding","camera_id":"$CAM","org_id":"$ORG","severity":"high","speed_kmh":42,"demo":true}
EOF
)
echo "Before:"
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -c "SELECT count(*) FROM events;"
docker exec citevision-v2-mosquitto mosquitto_pub -h 127.0.0.1 -p 1883 -t "cv/events/$CAM" -m "$PAYLOAD"
sleep 3
echo "After:"
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -c "SELECT event_type, count(*) FROM events GROUP BY 1;"
