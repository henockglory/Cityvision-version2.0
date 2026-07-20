#!/usr/bin/env bash
# Wait for a NEW Frigate event (age<=30s) on speed cam; dump detect state.
set -uo pipefail
FCAM=cv_55694d53-8f58-4981-91b2-7c6cd528a25d
echo "=== current detections ==="
curl -sf --max-time 5 "http://127.0.0.1:5000/api/${FCAM}/latest.jpg" -o /tmp/latest.jpg && ls -la /tmp/latest.jpg || echo no_latest
curl -sf --max-time 5 http://127.0.0.1:5000/api/stats -o /tmp/fs.json
python3 - <<PY
import json
d=json.load(open("/tmp/fs.json"))
c=(d.get("cameras") or {}).get("$FCAM") or {}
print("fps", c.get("camera_fps"), "det", c.get("detection_fps"), "pid", c.get("pid"))
print("detection", json.dumps(c.get("detection") or {}, indent=None)[:300])
# also top-level
print("det_fps service", (d.get("detectors") or {}))
PY

echo "=== poll for fresh event 3min ==="
for i in $(seq 1 36); do
  curl -sf --max-time 5 "http://127.0.0.1:5000/api/events?cameras=${FCAM}&limit=3" -o /tmp/fev.json || { echo fail; sleep 5; continue; }
  python3 - <<'PY'
import json,time
ev=json.load(open("/tmp/fev.json"))
now=time.time()
if not isinstance(ev,list) or not ev:
    print("n=0"); raise SystemExit(1)
for e in ev[:3]:
    st=e.get("start_time")
    age=now-float(st) if isinstance(st,(int,float)) else None
    print(f"  id={str(e.get('id'))[:28]} label={e.get('label')} age={age:.0f if age else None}s end={e.get('end_time')}")
young=min((now-float(e['start_time'])) for e in ev if isinstance(e.get('start_time'),(int,float)))
raise SystemExit(0 if young<=30 else 1)
PY
  if [ $? -eq 0 ]; then echo "[OK] fresh event"; exit 0; fi
  sleep 5
done
echo "[FAIL] no fresh event"
exit 1
