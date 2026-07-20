#!/usr/bin/env bash
set -uo pipefail
CAM=cv_8ed20433-57d5-4999-a6ab-0bea028b23a3
python3 - <<PY
import json,urllib.request,time
cam="$CAM"
with urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={cam}&limit=8", timeout=10) as r:
    ev=json.loads(r.read().decode())
now=time.time()
print("n", len(ev))
for e in ev[:8]:
    data=e.get("data") or {}
    box=data.get("box")
    print(f"age={now-float(e['start_time']):5.0f}s end={e.get('end_time') is not None} clip={e.get('has_clip')} snap={e.get('has_snapshot')} label={e.get('label')} box={box}")
# stats
with urllib.request.urlopen("http://127.0.0.1:5000/api/stats", timeout=8) as r:
    st=json.loads(r.read().decode())
c=(st.get("cameras") or {}).get(cam) or {}
print("fps", c.get("camera_fps"), "det", c.get("detection_fps"), "rec", c.get("recording"))
PY

# Compare AI bbox vs frigate for a recent violation
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT left(payload::text,300) FROM events WHERE event_type='red_light_violation' ORDER BY ingested_at DESC LIMIT 1;"
