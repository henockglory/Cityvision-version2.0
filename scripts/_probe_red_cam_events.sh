#!/usr/bin/env bash
set -uo pipefail
# Probe why red-light cam has det but no events
CAM=cv_8ed20433-57d5-4999-a6ab-0bea028b23a3
echo "=== events red ==="
curl -sf --max-time 8 "http://127.0.0.1:5000/api/events?cameras=${CAM}&limit=10" | python3 -c 'import json,sys,time;e=json.load(sys.stdin);print("n",len(e));now=time.time();
[print(now-float(x["start_time"]), x.get("label"), x.get("zones"), x.get("end_time")) for x in e[:10]]'

echo "=== review red ==="
curl -sf --max-time 8 "http://127.0.0.1:5000/api/review?cameras=${CAM}&limit=5" | python3 -c 'import json,sys,time;e=json.load(sys.stdin);print("n",len(e));now=time.time();
[print(now-float(x.get("start_time") or 0), x.get("severity"), (x.get("data") or {}).get("objects")) for x in e[:5]]'

echo "=== latest objects debug ==="
curl -sf --max-time 8 "http://127.0.0.1:5000/api/${CAM}/latest.jpg" -o /tmp/red_latest.jpg && ls -la /tmp/red_latest.jpg
# try detections endpoint
curl -sf --max-time 8 "http://127.0.0.1:5000/api/${CAM}" | head -c 800; echo

echo "=== config zones coords (red) ==="
python3 - <<'PY'
import yaml
cfg=yaml.safe_load(open("/home/gheno/citevision-v2/infra/frigate-config/config.yml"))
c=cfg["cameras"]["cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"]
print("ffmpeg", (c.get("ffmpeg") or {}).get("inputs"))
print("zones:")
for zn,zv in (c.get("zones") or {}).items():
    print(" ", zn, "coords", zv.get("coordinates"), "obj", zv.get("objects"))
print("objects", c.get("objects"))
print("record", c.get("record"))
print("snapshots", c.get("snapshots"))
print("motion", list((c.get("motion") or {}).keys()))
PY

echo "=== counting events ==="
curl -sf "http://127.0.0.1:5000/api/events?cameras=cv_9a3cd323-3820-46f0-aa5b-86c086a4a782&limit=5" | python3 -c 'import json,sys,time;e=json.load(sys.stdin);print("n",len(e));now=time.time();
[print(now-float(x["start_time"]), x.get("label"), x.get("end_time") is None) for x in e[:5]]'
