#!/usr/bin/env python3
"""Read-only probe: bridge MQTT counters + fresh Frigate car events for the feu camera."""
import json
import time
import urllib.request

AI = "http://127.0.0.1:8001"
FRIGATE = "http://127.0.0.1:5000"
CAM = "cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"


def get(url: str):
    with urllib.request.urlopen(url, timeout=8) as resp:
        return json.load(resp)


def walk(obj, keys, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(s in str(k) for s in keys) and isinstance(v, (int, float, str, bool)):
                print(f"{prefix}{k} = {v}")
            walk(v, keys, prefix + str(k) + ".")


blockers = get(f"{AI}/debug/rule-blockers")
walk(blockers, ["mqtt", "handled", "poll", "enqueued", "memory", "skipped"])

print("---EVENTS---")
now = time.time()
evs = get(f"{FRIGATE}/api/events?camera={CAM}&limit=5")
for e in evs:
    end = e.get("end_time")
    age = None if end is None else round(now - float(end), 1)
    print(e.get("id"), e.get("label"), "end_age_s=", age, "zones=", (e.get("zones") or [])[:3])
