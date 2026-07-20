#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

echo "=== frigate container ==="
docker ps -a --filter name=citevision-v2-frigate --format '{{.Status}} {{.Names}}'
docker ps -a --filter name=citevision-v2-go2rtc --format '{{.Status}} {{.Names}}'

echo "=== recreate go2rtc+frigate ==="
cd infra
docker compose --env-file "$ROOT/.env" up -d --force-recreate go2rtc
sleep 5
docker compose --env-file "$ROOT/.env" up -d --force-recreate frigate
cd "$ROOT"

echo "=== wait API ==="
for i in $(seq 1 90); do
  if timeout 4 curl -sf http://127.0.0.1:5000/api/version >/dev/null; then
    echo "up $(curl -sf http://127.0.0.1:5000/api/version) try=$i"
    break
  fi
  sleep 2
done

echo "=== register streams ==="
bash scripts/ensure-demo-streams.sh || true
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams; echo
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial; echo

echo "=== wait 45s for detections ==="
sleep 45

echo "=== stats ==="
curl -sf --max-time 10 http://127.0.0.1:5000/api/stats > /tmp/fst.json || { echo stats_fail; docker logs --tail 40 citevision-v2-frigate; exit 1; }
python3 - <<'PY'
import json
d=json.load(open("/tmp/fst.json"))
for k,v in (d.get("cameras") or {}).items():
    print(k[:48], "fps", v.get("camera_fps"), "det", v.get("detection_fps"))
PY

echo "=== events ==="
curl -sf --max-time 15 'http://127.0.0.1:5000/api/events?limit=20' > /tmp/fev.json || { echo events_fail; exit 1; }
python3 - <<'PY'
import json,time
evs=json.load(open("/tmp/fev.json"))
if not isinstance(evs, list):
    print("raw keys", list(evs)[:8] if isinstance(evs,dict) else type(evs))
    evs = evs.get("events") or []
now=time.time()
print("n", len(evs))
ages=[]
for e in evs[:20]:
    st=float(e.get("start_time") or 0)
    age=now-st
    ages.append(age)
    print(f"{age:7.0f}s  {str(e.get('camera',''))[:48]}  {e.get('label')}")
print("youngest", min(ages) if ages else None)
PY

echo "=== review/summary if any ==="
curl -sf --max-time 8 'http://127.0.0.1:5000/api/review?limit=5' | head -c 500; echo
curl -sf --max-time 8 http://127.0.0.1:5000/api/version; echo
docker logs --tail 30 citevision-v2-frigate 2>&1 | tail -30
