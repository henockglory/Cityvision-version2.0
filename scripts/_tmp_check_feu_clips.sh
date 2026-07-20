#!/usr/bin/env bash
set -uo pipefail
echo "UI $(curl -sf --max-time 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:5174/ || echo DOWN)"
echo "BE $(curl -sf --max-time 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8081/health || echo DOWN)"
echo "AI $(curl -sf --max-time 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/health || echo DOWN)"
echo "FR $(curl -sf --max-time 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:5000/api/version || echo DOWN)"

FC=cv_8ed20433-57d5-4999-a6ab-0bea028b23a3
python3 - <<PY
import json, urllib.request, time
fc="$FC"
try:
  st=json.loads(urllib.request.urlopen("http://127.0.0.1:5000/api/stats",timeout=8).read())
  cam=(st.get("cameras") or {}).get(fc) or {}
  print(f"frigate fps={cam.get('camera_fps')} det={cam.get('detection_fps')} record={cam.get('recording')}")
except Exception as e:
  print("stats", e)
ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=5",timeout=10).read())
now=time.time()
for e in ev or []:
  age=now-float(e.get("start_time") or 0)
  end=e.get("end_time")
  eid=e["id"]
  for path in ("clip.mp4","snapshot.jpg","thumbnail.jpg"):
    code="?"
    try:
      req=urllib.request.Request(f"http://127.0.0.1:5000/api/events/{eid}/{path}")
      with urllib.request.urlopen(req, timeout=10) as r:
        code=f"{r.status}:{len(r.read(2048))}"
    except Exception as ex:
      code=str(ex)[:70]
    print(f"age={age:.0f}s end={end is not None} {path} -> {code}")
PY
