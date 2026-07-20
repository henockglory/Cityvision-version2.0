#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
CAM=55694d53-8f58-4981-91b2-7c6cd528a25d
FCAM=cv_${CAM}

echo "=== docker ps ==="
docker ps --format '{{.Names}} {{.Status}}' | grep -E 'go2rtc|frigate|postgres' || true

echo "=== go2rtc streams ==="
curl -sf --max-time 5 http://127.0.0.1:1984/api/streams -o /tmp/g2.json || { echo "go2rtc down"; docker logs --tail 40 citevision-v2-go2rtc; exit 1; }
python3 - <<'PY'
import json
d=json.load(open("/tmp/g2.json"))
print("n", len(d))
for k,v in d.items():
    producers=(v or {}).get("producers") or []
    consumers=(v or {}).get("consumers") or []
    print(f"  {k}: producers={len(producers)} consumers={len(consumers)}")
    for p in producers[:1]:
        print("   src=", (p.get("url") or p.get("remote_addr") or p) )
PY

echo "=== frigate config cameras (grep) ==="
grep -E '^\s+cv_|rtsp://|ffmpeg:' -A2 "$ROOT/infra/frigate-config/config.yml" | head -80

echo "=== wait fps > 0 ==="
for i in $(seq 1 24); do
  curl -sf --max-time 5 http://127.0.0.1:5000/api/stats -o /tmp/fs.json || { echo "try $i stats fail"; sleep 5; continue; }
  python3 - <<PY
import json
d=json.load(open("/tmp/fs.json"))
cams=d.get("cameras") or {}
fc="$FCAM"
v=cams.get(fc) or {}
fps=float(v.get("camera_fps") or 0)
print(f"try fps={fps} det={v.get('detection_fps')}")
raise SystemExit(0 if fps>0 else 1)
PY
  rc=$?
  if [ $rc -eq 0 ]; then echo "[OK] fps up"; break; fi
  sleep 5
done

echo "=== repair demo streams ==="
curl -sS -w "\nHTTP=%{http_code}\n" --max-time 60 -X POST \
  -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true

echo "=== resync spatial ==="
curl -sS -w "\nHTTP=%{http_code}\n" --max-time 60 -X POST \
  -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial || true

sleep 20

echo "=== stats after repair ==="
curl -sf --max-time 8 http://127.0.0.1:5000/api/stats -o /tmp/fs.json
python3 - <<PY
import json,time
d=json.load(open("/tmp/fs.json"))
cams=d.get("cameras") or {}
print("n", len(cams))
for k,v in cams.items():
    print(f"  {k}: fps={v.get('camera_fps')} det={v.get('detection_fps')}")
PY

echo "=== events age ==="
curl -sf --max-time 8 "http://127.0.0.1:5000/api/events?cameras=${FCAM}&limit=5" -o /tmp/fev.json || echo events_fail
python3 - <<'PY'
import json,time
try:
  ev=json.load(open("/tmp/fev.json"))
except Exception as e:
  print("parse", e); raise SystemExit(0)
now=time.time()
if not isinstance(ev,list) or not ev:
  print("events=0"); raise SystemExit(0)
ages=[now-float(e["start_time"]) for e in ev if isinstance(e.get("start_time"),(int,float))]
print("youngest", min(ages) if ages else None, "n", len(ev))
print("sample_label", (ev[0].get("label"), ev[0].get("id")))
PY

echo "=== frigate logs tail ==="
docker logs --tail 30 citevision-v2-frigate 2>&1 | tail -30
