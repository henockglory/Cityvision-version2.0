import json
import subprocess
import time
import urllib.request
from collections import Counter

import cv2
import numpy as np

from citevision_ai.road_enforcement.traffic_light import (
    _polygon_pixel_bbox,
    classify_light_color,
)

sql = (
    "SELECT polygon::text FROM zones "
    "WHERE camera_id='8ed20433-57d5-4999-a6ab-0bea028b23a3' "
    "AND zone_kind='traffic_light_color';"
)
poly = json.loads(
    subprocess.check_output(
        [
            "docker",
            "exec",
            "citevision-v2-postgres",
            "psql",
            "-U",
            "citevision",
            "-d",
            "citevision",
            "-t",
            "-A",
            "-c",
            sql,
        ],
        text=True,
    ).strip()
)
fc = "cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"
url = f"http://127.0.0.1:5000/api/{fc}/latest.jpg"
states = []
for i in range(120):
    try:
        data = urllib.request.urlopen(url, timeout=8).read()
        frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception as e:
        print("err", e)
        time.sleep(1)
        continue
    if frame is None:
        continue
    h, w = frame.shape[:2]
    box = _polygon_pixel_bbox(poly, w, h)
    x1, y1, x2, y2 = box
    state, ratios = classify_light_color(frame[y1:y2, x1:x2])
    states.append(state)
    if state != "green" or i % 20 == 0:
        nice = {k: round(v, 4) for k, v in ratios.items()}
        print(i, state, nice)
    time.sleep(1)
print("COUNTS", Counter(states))
