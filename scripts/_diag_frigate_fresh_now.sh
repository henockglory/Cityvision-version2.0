#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

echo "=== go2rtc streams ==="
curl -sf --max-time 5 http://127.0.0.1:1984/api/streams 2>/dev/null | python3 -c '
import json,sys
d=json.load(sys.stdin)
print("n", len(d))
for k,v in list(d.items())[:12]:
    print(k, "->", (v.get("producers") or v.get("url") or list(v.keys())[:3]))
' || echo go2rtc_down

echo "=== frigate stats ==="
curl -sf --max-time 8 http://127.0.0.1:5000/api/stats | python3 -c '
import json,sys
d=json.load(sys.stdin)
cams=d.get("cameras") or {}
print("frigate_cams", len(cams))
for k,v in cams.items():
    print(k[:48], "fps", v.get("camera_fps"), "det", v.get("detection_fps"), "pid", v.get("pid"))
' || echo frigate_stats_fail

echo "=== frigate events ages ==="
curl -sf --max-time 8 'http://127.0.0.1:5000/api/events?limit=10' | python3 -c '
import json,sys,time
d=json.load(sys.stdin)
evs=d if isinstance(d,list) else []
now=time.time()
for e in evs[:10]:
    st=e.get("start_time") or 0
    print(f"{now-st:7.0f}s  cam={str(e.get(\"camera\",\"\"))[:40]}  label={e.get(\"label\")}")
' || echo events_fail

echo "=== AI cameras ==="
curl -sf http://127.0.0.1:8001/cameras | python3 -c '
import json,sys
d=json.load(sys.stdin)
cams=d.get("cameras") or []
print("n", len(cams))
for c in cams[:10]:
    print(c.get("camera_id"), "run", c.get("running"), "fp", c.get("frames_processed"), "err", c.get("last_error"))
'

echo "=== ensure-demo-streams ==="
bash scripts/ensure-demo-streams.sh || true

echo "=== repair + resync ==="
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams; echo
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial; echo

sleep 8
echo "=== AI after resync ==="
curl -sf http://127.0.0.1:8001/cameras | python3 -c '
import json,sys
d=json.load(sys.stdin)
cams=d.get("cameras") or []
print("n", len(cams))
for c in cams[:10]:
    print(c.get("camera_id"), "run", c.get("running"), "fp", c.get("frames_processed"), "err", c.get("last_error"))
'

echo "=== ffprobe first go2rtc stream ==="
STREAM=$(curl -sf http://127.0.0.1:1984/api/streams | python3 -c 'import json,sys;d=json.load(sys.stdin);print(next(iter(d),""))')
echo "stream=$STREAM"
if [[ -n "$STREAM" ]]; then
  timeout 8 ffprobe -v error -rtsp_transport tcp -i "rtsp://127.0.0.1:8554/$STREAM" 2>&1 | head -15 || echo ffprobe_fail
fi
