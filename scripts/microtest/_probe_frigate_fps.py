#!/usr/bin/env python3
"""Read-only probe: Frigate per-camera fps/detection stats for the feu camera."""
import json
import urllib.request

CAM = "cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"

with urllib.request.urlopen("http://127.0.0.1:5000/api/stats", timeout=8) as resp:
    stats = json.load(resp)

cams = stats.get("cameras") or {}
cam = cams.get(CAM) or {}
for key in ("camera_fps", "detection_fps", "process_fps", "skipped_fps", "pid", "detection_enabled"):
    print(f"{key}: {cam.get(key)}")
print("detectors:", json.dumps(stats.get("detectors") or {}, default=str)[:200])
