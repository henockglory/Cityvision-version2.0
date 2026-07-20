#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2
curl -sf --max-time 8 http://127.0.0.1:5000/api/stats -o /tmp/frigate_stats.json
python3 <<'PY'
import json
d=json.load(open("/tmp/frigate_stats.json"))
cams=d.get("cameras") or {}
print("cams", list(cams.keys())[:30])
for k,v in list(cams.items())[:15]:
    print(f"  {k}: fps={v.get('camera_fps')} det={v.get('detection_fps')} pid={v.get('pid')}")
PY
curl -sf --max-time 8 'http://127.0.0.1:5000/api/events?limit=10' -o /tmp/frigate_events.json
python3 <<'PY'
import json
ev=json.load(open("/tmp/frigate_events.json"))
print("events", len(ev) if isinstance(ev,list) else type(ev))
if isinstance(ev,list):
  for e in ev[:10]:
    print(" ", e.get("camera"), e.get("label"), e.get("start_time"))
PY
curl -sf --max-time 5 http://127.0.0.1:1984/api/streams -o /tmp/go2rtc_streams.json
python3 <<'PY'
import json
d=json.load(open("/tmp/go2rtc_streams.json"))
keys=list(d.keys()) if isinstance(d,dict) else []
print("go2rtc n=", len(keys))
print("demo=", [k for k in keys if str(k).startswith("demo-")][:20])
PY
