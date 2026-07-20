#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

echo "=== events (all, limit 15) ==="
curl -sf --max-time 10 'http://127.0.0.1:5000/api/events?limit=15' > /tmp/fev.json || { echo events_http_fail; curl -sS --max-time 10 'http://127.0.0.1:5000/api/events?limit=5' | head -c 400; echo; exit 0; }
python3 - <<'PY'
import json,time
evs=json.load(open("/tmp/fev.json"))
if not isinstance(evs,list):
    print("type", type(evs), list(evs)[:5] if isinstance(evs,dict) else evs)
    evs=evs.get("events") or evs.get("data") or []
now=time.time()
print("n", len(evs))
for e in evs[:15]:
    st=float(e.get("start_time") or 0)
    print(f"{now-st:7.0f}s  cam={str(e.get('camera',''))[:48]}  label={e.get('label')}  id={str(e.get('id',''))[:16]}")
PY

echo "=== events for red cam ==="
CAM='cv_8ed20433-57d5-4999-a6ab-0bea028b23a3'
curl -sf --max-time 10 "http://127.0.0.1:5000/api/events?cameras=${CAM}&limit=10" > /tmp/fev2.json || echo fail
python3 - <<PY
import json,time
evs=json.load(open("/tmp/fev2.json"))
if not isinstance(evs,list):
    evs=evs.get("events") or []
now=time.time()
print("n", len(evs))
for e in evs[:10]:
    st=float(e.get("start_time") or 0)
    print(f"{now-st:7.0f}s  label={e.get('label')}  id={str(e.get('id',''))[:16]}")
PY

echo "=== frigate config cameras keys ==="
docker exec citevision-v2-frigate sh -c 'python3 -c "import yaml;d=yaml.safe_load(open(\"/config/config.yml\"));print(list((d.get(\"cameras\") or {}).keys()))"' 2>/dev/null || \
  grep -E '^\s{0,2}[a-zA-Z0-9_-]+:' /home/gheno/citevision-v2/infra/frigate-config/config.yml | head -30

echo "=== validate proc ==="
pgrep -af 'validate_rule|_validate_rule_frigate|heal_validate' | grep -v pgrep | head -8
