#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

echo "=== docker ==="
docker ps -a --format '{{.Names}} {{.Status}}' | grep -E 'frigate|go2rtc' || true

# Start/restart frigate+go2rtc if needed
docker start citevision-v2-go2rtc 2>/dev/null || true
docker start citevision-v2-frigate 2>/dev/null || true
# If already running but API down, restart
if ! curl -sf --max-time 3 http://127.0.0.1:5000/api/version >/dev/null; then
  echo "frigate API down — restart"
  docker restart citevision-v2-go2rtc citevision-v2-frigate
fi
for i in $(seq 1 40); do
  if curl -sf --max-time 3 http://127.0.0.1:5000/api/version >/dev/null; then
    echo "frigate up try=$i"
    break
  fi
  sleep 3
done

curl -sS -w "\nHTTP=%{http_code}\n" --max-time 60 -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/demo/repair-streams
sleep 20

curl -sf http://127.0.0.1:5000/api/stats -o /tmp/fs.json
python3 - <<'PY'
import json,time,urllib.request
d=json.load(open("/tmp/fs.json"))
cams=d.get("cameras") or {}
fc="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
print("n", len(cams))
for k,v in cams.items():
    print(f"  {k}: fps={v.get('camera_fps')} det={v.get('detection_fps')}")
# wait fresh
ok=False
for i in range(24):
    ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=3", timeout=8).read())
    now=time.time()
    if isinstance(ev,list) and ev:
        young=min(now-float(e["start_time"]) for e in ev if isinstance(e.get("start_time"),(int,float)))
        print(f"try {i} youngest={young:.0f}s clip={ev[0].get('has_clip')}")
        if young<=40:
            ok=True; break
    time.sleep(5)
print("FRESH", "OK" if ok else "FAIL")
raise SystemExit(0 if ok else 2)
PY
