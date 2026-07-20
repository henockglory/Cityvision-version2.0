#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

echo "=== re-register streams ==="
bash scripts/ensure-demo-streams.sh

echo "=== ffprobe RTSP ==="
timeout 12 ffprobe -v error -rtsp_transport tcp -show_entries stream=codec_type,width,height \
  -of csv=p=0 -i "rtsp://127.0.0.1:8554/demo-74d51ead-aaea7c30" 2>&1 | head -20 || echo FAIL_PROBE

echo "=== frigate rebuild + restart ==="
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild" -H "X-Internal-Key: $KEY" || true
echo
docker restart citevision-v2-frigate
for i in $(seq 1 40); do
  curl -sf http://127.0.0.1:5000/api/version >/dev/null 2>&1 && break
  sleep 2
done
echo "frigate version=$(curl -sf http://127.0.0.1:5000/api/version || echo down)"

echo "=== restart AI ingest ==="
python3 scripts/_restart_ai.py || true
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial" -H "X-Internal-Key: $KEY" || true
echo
sleep 15

echo "=== AI cameras ==="
curl -sS http://127.0.0.1:8001/cameras | python3 -c '
import json,sys
d=json.load(sys.stdin)
for c in d.get("cameras") or []:
  print("cam", c.get("camera_id")[:8], "running", c.get("running"), "frames_read", c.get("frames_read"), "err", (c.get("last_error") or "")[:80])
'

echo "=== wait frames ==="
for i in $(seq 1 12); do
  fr=$(curl -sS http://127.0.0.1:8001/cameras | python3 -c 'import json,sys; d=json.load(sys.stdin); print(sum(int(c.get("frames_read") or 0) for c in (d.get("cameras") or [])))')
  echo "t=${i} frames_read_sum=$fr"
  if [[ "${fr:-0}" -ge 6 ]]; then
    echo INGEST_OK
    break
  fi
  sleep 5
done

echo "=== Frigate fps ==="
sleep 10
curl -sS http://127.0.0.1:5000/api/stats | python3 -c '
import json,sys
d=json.load(sys.stdin)
for k,v in (d.get("cameras") or {}).items():
  print(k[:36], "fps", v.get("camera_fps"), "det", v.get("detection_fps"))
' 2>/dev/null || echo stats_fail

# ensure vite still up
curl -sf -o /dev/null -w "ui=%{http_code}\n" http://127.0.0.1:5174/ || {
  echo "restart vite"
  cd "$ROOT/frontend"
  nohup npm run dev -- --host 127.0.0.1 --port 5174 > /tmp/citevision-vite.log 2>&1 &
  sleep 3
}
