#!/usr/bin/env python3
import json, urllib.request
cam = "cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"
for key in ("camera", "cameras", "cam_id"):
    url = f"http://127.0.0.1:5000/api/events?{key}={cam}&limit=5"
    try:
        ev = json.loads(urllib.request.urlopen(url, timeout=10).read())
        print(key, len(ev))
    except Exception as e:
        print(key, "ERR", e)
