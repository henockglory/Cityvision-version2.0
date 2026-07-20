#!/usr/bin/env bash
# Diagnose + heal Frigate demo cameras (WSL native Docker only).
set -euo pipefail
ROOT=~/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh 2>/dev/null || true
ENV_FILE="$(ensure_env_file "$ROOT" 2>/dev/null || echo "$ROOT/.env")"
# shellcheck disable=SC1090
set -a; [ -f "$ENV_FILE" ] && . "$ENV_FILE"; set +a
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

echo "=== Frigate version ==="
curl -sf --max-time 5 http://127.0.0.1:5000/api/version || echo FAIL

echo ""
echo "=== Frigate cameras/stats (keys) ==="
curl -sf --max-time 8 http://127.0.0.1:5000/api/stats | python3 -c '
import sys,json
d=json.load(sys.stdin)
cams=d.get("cameras") or {}
print("cameras:", list(cams.keys())[:20])
for k,v in list(cams.items())[:8]:
    print(f"  {k}: fps={v.get(\"camera_fps\")} det={v.get(\"detection_fps\")} pid={v.get(\"pid\")}")
' 2>/dev/null || echo "stats parse fail"

echo ""
echo "=== Recent Frigate events count ==="
curl -sf --max-time 8 'http://127.0.0.1:5000/api/events?limit=5' | python3 -c '
import sys,json
ev=json.load(sys.stdin)
print("n=", len(ev) if isinstance(ev,list) else type(ev))
if isinstance(ev,list):
  for e in ev[:5]:
    print(" ", e.get("camera"), e.get("label"), e.get("start_time"))
' 2>/dev/null || echo "events fail"

echo ""
echo "=== go2rtc streams ==="
curl -sf --max-time 5 http://127.0.0.1:1984/api/streams | python3 -c '
import sys,json
d=json.load(sys.stdin)
keys=list(d.keys()) if isinstance(d,dict) else []
print("n=", len(keys))
print("demo=", [k for k in keys if k.startswith("demo-")][:12])
' 2>/dev/null || echo "go2rtc fail"

echo ""
echo "=== heal: repair-streams + frigate rebuild ==="
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true
echo
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild || true
echo
echo "restarting frigate container…"
docker restart citevision-v2-frigate >/dev/null
for i in $(seq 1 40); do
  curl -sf --max-time 3 http://127.0.0.1:5000/api/version >/dev/null 2>&1 && break
  sleep 2
done
curl -sf http://127.0.0.1:5000/api/version && echo " Frigate up" || echo " Frigate still down"
sleep 25
echo "=== events after heal ==="
curl -sf --max-time 8 'http://127.0.0.1:5000/api/events?limit=8' | python3 -c '
import sys,json
ev=json.load(sys.stdin)
print("n=", len(ev) if isinstance(ev,list) else 0)
if isinstance(ev,list):
  for e in ev[:8]:
    print(" ", e.get("camera"), e.get("label"), e.get("start_time"))
' 2>/dev/null || echo "events fail"
