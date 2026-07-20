#!/usr/bin/env python3
import json
import subprocess
import time
import urllib.request

API = "http://127.0.0.1:8081"
AI = "http://127.0.0.1:8001"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
CAM = "01ee632c-271c-4e66-ba98-3d1d7e430c09"
LOG = "/home/gheno/citevision-v2/logs/rules-engine.log"


def get(url, headers=None, data=None):
    hdrs = dict(headers or {})
    body = data.encode() if isinstance(data, str) else data
    req = urllib.request.Request(url, data=body, headers=hdrs)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


for i in range(8):
    cams = get(f"{AI}/cameras")
    cam = next((c for c in cams.get("cameras", []) if c["camera_id"] == CAM), {})
    print(f"poll {i+1}: frames={cam.get('frames_processed')} fps={cam.get('fps')}")
    out = subprocess.run(["grep", "rule.*matched", LOG], capture_output=True, text=True)
    lines = [ln for ln in (out.stdout or "").split("\n") if ln][-3:]
    for ln in lines:
        print(" ", ln.strip()[-100:])
    time.sleep(30)

print("\n=== final observe ===")
subprocess.run(["python3", "/home/gheno/citevision-v2/scripts/_observe_speed_alerts.py"])
