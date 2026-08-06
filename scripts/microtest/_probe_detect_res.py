#!/usr/bin/env python3
"""Read-only probe: Frigate detect resolution + a live MQTT-style box sample."""
import json

CAM = "cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"

with open("/tmp/frigate_config.json", encoding="utf-8") as fh:
    cfg = json.load(fh)

cam = (cfg.get("cameras") or {}).get(CAM) or {}
det = cam.get("detect") or {}
print("detect:", det.get("width"), "x", det.get("height"), "fps:", det.get("fps"))
zones = cam.get("zones") or {}
for name, z in zones.items():
    coords = z.get("coordinates")
    print("frigate zone:", name, "coords:", str(coords)[:120])
