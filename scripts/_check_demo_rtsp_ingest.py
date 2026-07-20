#!/usr/bin/env python3
import json, time, urllib.request

time.sleep(15)
cams = json.loads(urllib.request.urlopen("http://127.0.0.1:8001/cameras", timeout=10).read())["cameras"]
for c in cams:
    if c.get("camera_id", "").startswith("8ed"):
        print("feux ingest:", json.dumps(c, indent=2))
stats = json.loads(urllib.request.urlopen("http://127.0.0.1:5000/api/stats", timeout=10).read())
feux = stats.get("cameras", {}).get("cv_8ed20433-57d5-4999-a6ab-0bea028b23a3", {})
print("frigate feux fps:", feux.get("camera_fps"), "det:", feux.get("detection_fps"))
