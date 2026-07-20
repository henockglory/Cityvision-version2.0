#!/usr/bin/env python3
import subprocess, json, urllib.request, time

# Deploy zone_speed
r = subprocess.run(
    ["cp",
     "/mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/analytics/zone_speed.py",
     "/home/gheno/citevision-v2/ai-engine/src/citevision_ai/analytics/zone_speed.py"],
    capture_output=True, text=True
)
print("zone_speed deploy:", r.returncode)

# Check cameras
resp = urllib.request.urlopen("http://127.0.0.1:8001/cameras", timeout=5)
d = json.load(resp)
cams = d.get("cameras", [])
print(f"cameras: {len(cams)}")
for c in cams:
    print(f"  running={c.get('running')} frames={c.get('frames_processed')}")

# Wait 15s and show zone_speed debug
time.sleep(15)
r2 = subprocess.run(
    ["grep", "-E", "zone_speed_debug|circuit-breaker OPEN",
     "/home/gheno/citevision-v2/logs/ai-engine.log"],
    capture_output=True, text=True
)
lines = r2.stdout.strip().splitlines()
print(f"\nzone_speed_debug ({len(lines)} lignes):")
for l in lines[-10:]:
    print(" ", l[-120:])
