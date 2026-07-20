#!/usr/bin/env bash
set -uo pipefail
ORG=74d51ead-97a7-4e41-a488-503a9b90c466
API=http://127.0.0.1:8081

echo "=== demo settings ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
"SELECT source_mode, active_video_id, active_camera_id, pipeline_status FROM org_demo_settings WHERE org_id='$ORG'::uuid;"

echo "=== cameras + demo_video ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
"SELECT left(c.id::text,8) cam, c.name, c.metadata->>'demo_video_id' vid,
  left(c.metadata->>'go2rtc_src',40) gsrc
 FROM cameras c WHERE c.org_id='$ORG'::uuid ORDER BY c.name;"

echo "=== AI now ==="
curl -sS http://127.0.0.1:8001/cameras | python3 -c '
import json,sys
for c in json.load(sys.stdin).get("cameras") or []:
  print(c["camera_id"], c.get("rtsp_url"), "fr", c.get("frames_read"), "fp", c.get("frames_processed"))
'

echo "=== validate still running? ==="
pgrep -af 'validate_rule|1hit|validate_all' | grep -v pgrep | head -10
tail -15 /home/gheno/citevision-v2/logs/validate-all-5.log
