#!/usr/bin/env python3
"""Verify zones on all active AI cameras."""
import urllib.request, json, sys

try:
    with urllib.request.urlopen("http://127.0.0.1:8001/cameras", timeout=8) as r:
        d = json.loads(r.read())
except Exception as e:
    print(f"FAIL: {e}"); sys.exit(1)

cams = d.get("cameras") or []
print(f"Active cameras: {len(cams)}")
for cam in cams:
    cid = cam.get("camera_id","?")[:8]
    proc = cam.get("frames_processed", cam.get("processed", "?"))
    sc = cam.get("spatial_config") or {}
    zones = sc.get("zones") or []
    behaviors = sorted({z.get("behavior","?") for z in zones})
    print(f"  cam={cid} processed={proc} zones={len(zones)} behaviors={behaviors}")
