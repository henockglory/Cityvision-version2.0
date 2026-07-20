#!/usr/bin/env python3
"""Check what zones/behaviors are active for the cabin camera (f691)."""
import urllib.request, json, sys

CABIN_CAM = "f691ef55-6791-495b-a35e-be215e7ac109"
AI_URL = "http://127.0.0.1:8001"

# Get all cameras list
try:
    with urllib.request.urlopen(f"{AI_URL}/cameras", timeout=8) as r:
        d = json.loads(r.read())
except Exception as e:
    print(f"FAIL cameras list: {e}")
    sys.exit(1)

cams = d.get("cameras") or []
cabin = [c for c in cams if str(c.get("camera_id","")).startswith("f691ef55")]
if not cabin:
    print("Cabin camera not in AI cameras list!")
    print("All cameras:", [c.get("camera_id","")[:8] for c in cams])
    sys.exit(1)

c = cabin[0]
print(f"Camera: {c.get('camera_id','?')[:8]}")
print(f"Running: {c.get('running')}")
print(f"Frames processed: {c.get('frames_processed')}")
print(f"Frames read: {c.get('frames_read')}")

# Get spatial config
sc = c.get("spatial_config") or {}
zones = sc.get("zones") or []
behaviors = set(z.get("behavior","") for z in zones)
print(f"Zones ({len(zones)}):")
for z in zones:
    print(f"  - {z.get('name','?')} behavior={z.get('behavior','?')}")
print(f"Behaviors: {sorted(behaviors)}")
print()
print("seatbelt zone present:", any(z.get("behavior") == "seatbelt" for z in zones))
print("phone_use zone present:", any(z.get("behavior") == "phone_use" for z in zones))
print("speed_measurement zone present:", any(z.get("behavior") == "speed_measurement" for z in zones))
