#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

echo "=== ensure-demo-streams ==="
bash scripts/ensure-demo-streams.sh || true

echo "=== repair-streams + frigate rebuild ==="
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/demo/repair-streams" \
  -H "X-Internal-Key: $KEY" || true
echo
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild" \
  -H "X-Internal-Key: $KEY" || true
echo

echo "=== probe RTSP stream ==="
# timeout ffprobe
timeout 8 ffprobe -v error -rtsp_transport tcp -i "rtsp://127.0.0.1:8554/demo-74d51ead-aaea7c30" 2>&1 | head -20 || echo "ffprobe_fail"

echo "=== ensure-demo-pipeline ==="
bash scripts/ensure-demo-pipeline.sh || true

echo "=== AI cameras after heal ==="
curl -sS http://127.0.0.1:8001/cameras | python3 -c '
import json,sys
d=json.load(sys.stdin)
for c in d.get("cameras") or []:
  print(c.get("camera_id"), "running", c.get("running"), "frames_read", c.get("frames_read"), "err", c.get("last_error"))
'

echo "=== Frigate cam fps ==="
curl -sS http://127.0.0.1:5000/api/stats | python3 -c '
import json,sys
d=json.load(sys.stdin)
cams=d.get("cameras") or {}
for k,v in cams.items():
  print(k[:40], "fps", v.get("camera_fps"), "det", v.get("detection_fps"), "rec", v.get("recording"))
' 2>/dev/null || echo stats_fail
