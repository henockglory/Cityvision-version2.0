#!/usr/bin/env bash
set -uo pipefail
ROOT=~/citevision-v2
cd "$ROOT"
export PYTHONPATH="$ROOT/ai-engine/src${PYTHONPATH:+:$PYTHONPATH}"

python3 - <<'PY'
import json, time, urllib.request
import numpy as np
import cv2
from citevision_ai.road_enforcement.traffic_light import classify_light_color, _polygon_pixel_bbox

# polygons from DB
import subprocess
sql = """SELECT name, zone_kind, polygon::text FROM zones WHERE camera_id='8ed20433-57d5-4999-a6ab-0bea028b23a3';"""
out = subprocess.check_output([
    "docker","exec","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-t","-A","-F","|","-c",sql
], text=True)
zones={}
for line in out.strip().splitlines():
    if not line.strip():
        continue
    name, kind, poly = line.split("|",2)
    zones[kind]=json.loads(poly)
    print("zone", name, kind, "pts", len(zones[kind]))

fc="cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"
# pull latest jpeg from frigate
url=f"http://127.0.0.1:5000/api/{fc}/latest.jpg"
hist=[]
for i in range(12):
    try:
        data=urllib.request.urlopen(url, timeout=8).read()
        arr=np.frombuffer(data, dtype=np.uint8)
        frame=cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception as e:
        print("snap err", e); time.sleep(1); continue
    if frame is None:
        print("decode fail"); time.sleep(1); continue
    h,w=frame.shape[:2]
    box=_polygon_pixel_bbox(zones.get("traffic_light_color") or [], w, h)
    if not box:
        print("no light box"); break
    x1,y1,x2,y2=box
    roi=frame[y1:y2,x1:x2]
    state, ratios=classify_light_color(roi)
    red_r=float(ratios.get("red",0)); green_r=float(ratios.get("green",0)); amber_r=float(ratios.get("amber",0))
    red_dom = red_r>=0.01 and red_r>=green_r*1.8 and red_r>=amber_r*1.25
    hist.append((state, ratios, red_dom))
    print(f"i={i} state={state} ratios={ {k:round(v,4) for k,v in ratios.items()} } red_dom={red_dom} roi={x2-x1}x{y2-y1}")
    # save one sample
    if i==0:
        cv2.imwrite("/tmp/feu_roi.jpg", roi)
        cv2.imwrite("/tmp/feu_full.jpg", frame)
    time.sleep(1.5)

from collections import Counter
print("states", Counter(s for s,_,_ in hist))
print("red_dom_true", sum(1 for *_,d in hist if d))
PY

echo "=== rules schema sample ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "\d rules" | head -35
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "SELECT name, is_enabled, left(definition::text,200) FROM rules WHERE org_id='74d51ead-97a7-4e41-a488-503a9b90c466' AND name ILIKE '%feu%';"
