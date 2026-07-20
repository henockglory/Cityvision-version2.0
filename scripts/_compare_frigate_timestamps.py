#!/usr/bin/env python3
import json, urllib.request

cam = "cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"
ev = json.loads(urllib.request.urlopen(
    f"http://127.0.0.1:5000/api/events?cameras={cam}&limit=10", timeout=10,
).read())
print("feux frigate events:", len(ev))
for e in ev[:5]:
    st = e.get("start_time")
    box = (e.get("data") or {}).get("box")
    print(" start", st, "label", e.get("label"), "box", box)

# sample anchors from logs
anchors = [1783809823.904, 1783809851.931]
if ev:
    for a in anchors:
        best = min(ev, key=lambda e: abs(float(e.get("start_time", 0)) - a))
        st = float(best.get("start_time", 0))
        print(f"anchor {a} nearest delta {abs(st-a):.2f}s start {st}")
