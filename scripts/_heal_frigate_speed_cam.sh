#!/usr/bin/env bash
# Heal Frigate for speed demo cam: correct rebuild path + wait fresh events.
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

CAM="${1:-55694d53-8f58-4981-91b2-7c6cd528a25d}"
FCAM="cv_${CAM}"

echo "=== rebuild (ingest path) ==="
curl -sS -w "\nHTTP=%{http_code}\n" --max-time 180 -X POST \
  -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild || true

echo "=== restart go2rtc+frigate ==="
docker restart citevision-v2-go2rtc citevision-v2-frigate
sleep 35

echo "=== stats ==="
curl -sf --max-time 8 http://127.0.0.1:5000/api/stats -o /tmp/frigate_stats.json
python3 - <<PY
import json
d=json.load(open("/tmp/frigate_stats.json"))
cams=d.get("cameras") or {}
print("n", len(cams))
fc="$FCAM"
for k,v in cams.items():
    mark=" <<" if k==fc else ""
    print(f"  {k}: fps={v.get('camera_fps')} det={v.get('detection_fps')}{mark}")
if fc not in cams:
    print("MISSING", fc)
    raise SystemExit(2)
PY

echo "=== wait fresh events for $FCAM ==="
ok=0
for i in $(seq 1 36); do
  curl -sf --max-time 8 "http://127.0.0.1:5000/api/events?cameras=${FCAM}&limit=5" -o /tmp/fev.json || { echo "try $i api fail"; sleep 5; continue; }
  python3 - <<'PY'
import json, time
ev=json.load(open("/tmp/fev.json"))
now=time.time()
if not isinstance(ev, list) or not ev:
    print("events=0")
    raise SystemExit(1)
ages=[now-float(e["start_time"]) for e in ev if isinstance(e.get("start_time"), (int,float))]
young=min(ages) if ages else 99999
print(f"events={len(ev)} youngest={young:.0f}s")
raise SystemExit(0 if young<=30 else 1)
PY
  if [ $? -eq 0 ]; then ok=1; break; fi
  sleep 5
done
[ "$ok" = 1 ] && echo "[OK] fresh" || echo "[WARN] still stale"
