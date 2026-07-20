#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
# Wait until a young event has a downloadable clip via urllib
"$ROOT/ai-engine/.venv/bin/python" - <<'PY'
import json, time, urllib.request, urllib.error
from citevision_ai.evidence.frigate_track_evidence import FrigateTrackEvidence
from citevision_ai.evidence.gate import default_evidence_policy

base="http://127.0.0.1:5000"
fc="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
cam="55694d53-8f58-4981-91b2-7c6cd528a25d"
org="74d51ead-97a7-4e41-a488-503a9b90c466"

eid=None
for i in range(36):
  ev=json.loads(urllib.request.urlopen(f"{base}/api/events?cameras={fc}&limit=5", timeout=8).read())
  now=time.time()
  # prefer ended events (end_time set) older than ~8s so clip is ready
  candidates=[]
  for e in ev:
    st=float(e["start_time"]); age=now-st
    et=e.get("end_time")
    if age<5: continue
    try:
      with urllib.request.urlopen(f"{base}/api/events/{e['id']}/clip.mp4", timeout=20) as r:
        data=r.read(2048)
      if len(data)>500:
        candidates.append((age, e))
        print(f"ready age={age:.0f}s id={e['id'][:22]} clip_peek={len(data)}")
        break
    except Exception as ex:
      print(f"not ready age={age:.0f}s code={getattr(ex,'code',ex)}")
  if candidates:
    eid=candidates[0][1]["id"]; break
  time.sleep(3)
else:
  raise SystemExit("no ready clip")

evt={
  "event_type":"speeding","event_id":f"prove-{int(time.time())}","track_id":99,
  "camera_id":cam,"org_id":org,"class_name":"car",
  "bbox":{"x":0.3,"y":0.3,"width":0.25,"height":0.25},
  "bbox_ts":time.time(),"frigate_event_id":eid,
}
ft=FrigateTrackEvidence()
pol=default_evidence_policy()
print("capturing with bound event", eid)
t0=time.time()
out=ft.capture(pol, evt, org_id=org, camera_id=cam)
print("elapsed", round(time.time()-t0,1))
if not out:
  raise SystemExit("capture None")
meta=out.get("meta") or {}
print("status", out.get("status"), "src", meta.get("capture_source"), "fev", meta.get("frigate_event_id"))
print("clip", len(out.get("clip_bytes") or b""), "scene", len(out.get("scene") or b""), "subject", len(out.get("subject") or b""), "plate", len(out.get("plate_jpeg") or b""))
assert meta.get("capture_source")=="frigate_track"
assert out.get("clip_bytes") and out.get("scene")
print("INPROCESS_OK")
PY
