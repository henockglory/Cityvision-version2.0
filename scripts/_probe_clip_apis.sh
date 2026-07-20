#!/usr/bin/env bash
set -uo pipefail
python3 - <<'PY'
import json,urllib.request,time
fc="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
base="http://127.0.0.1:5000"
ev=json.loads(urllib.request.urlopen(f"{base}/api/events?cameras={fc}&limit=5").read())
now=time.time()
for e in ev:
  eid=e["id"]; st=float(e["start_time"]); en=float(e.get("end_time") or st+3)
  age=now-st
  # event clip
  try:
    with urllib.request.urlopen(f"{base}/api/events/{eid}/clip.mp4", timeout=15) as r:
      ec, es = 200, len(r.read(1500))
  except Exception as ex:
    ec, es = getattr(ex,"code",0), 0
  # window clip
  s=max(0, st-0.4); ee=max(s+1, en+0.8)
  try:
    with urllib.request.urlopen(f"{base}/api/{fc}/start/{s:.3f}/end/{ee:.3f}/clip.mp4", timeout=30) as r:
      wc, ws = 200, len(r.read(1500))
  except Exception as ex:
    wc, ws = getattr(ex,"code",0), 0
  detail=json.loads(urllib.request.urlopen(f"{base}/api/events/{eid}").read())
  print(f"age={age:.0f}s event_clip={ec}/{es} window={wc}/{ws} has_clip={e.get('has_clip')} cam_field={detail.get('camera')} label={e.get('label')}")
PY
