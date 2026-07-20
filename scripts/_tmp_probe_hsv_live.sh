#!/usr/bin/env bash
set -uo pipefail
export PYTHONPATH=/home/gheno/citevision-v2/ai-engine/src
python3 - <<'PY'
import json, subprocess, time, urllib.request
import numpy as np
import cv2
from citevision_ai.road_enforcement.traffic_light import classify_light_color, _polygon_pixel_bbox

sql = """SELECT name, zone_kind, polygon::text FROM zones WHERE camera_id='8ed20433-57d5-4999-a6ab-0bea028b23a3';"""
out = subprocess.check_output([
    "docker","exec","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-t","-A","-F","|","-c",sql
], text=True)
zones = {}
for line in out.strip().splitlines():
    if not line.strip():
        continue
    name, kind, poly = line.split("|", 2)
    zones[kind] = json.loads(poly)
    print("zone", name, kind, "pts", len(zones[kind]))

fc = "cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"
url = f"http://127.0.0.1:5000/api/{fc}/latest.jpg"
from collections import Counter
states = []
for i in range(20):
    try:
        data = urllib.request.urlopen(url, timeout=8).read()
        frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception as e:
        print("snap", e); time.sleep(1); continue
    if frame is None:
        continue
    h, w = frame.shape[:2]
    box = _polygon_pixel_bbox(zones.get("traffic_light_color") or [], w, h)
    if not box:
        print("no box"); break
    x1,y1,x2,y2 = box
    state, ratios = classify_light_color(frame[y1:y2, x1:x2])
    states.append(state)
    print(f"i={i} state={state} r={{{k: round(v,4) for k,v in ratios.items()}}} roi={x2-x1}x{y2-y1}")
    time.sleep(0.8)
print("counts", Counter(states))
PY
