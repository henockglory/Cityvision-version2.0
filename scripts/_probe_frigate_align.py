#!/usr/bin/env python3
"""Quick live probe: Frigate correlate after demo timeline align."""
from __future__ import annotations

import json
import sys
import time
import urllib.request

sys.path.insert(0, "/home/gheno/citevision-v2/ai-engine/src")
from citevision_ai.config import settings
from citevision_ai.evidence.frigate_track_evidence import FrigateTrackEvidence

settings.frigate_enabled = True
settings.frigate_evidence = True
engine = FrigateTrackEvidence()
cam = "8ed20433-57d5-4999-a6ab-0bea028b23a3"
fid = f"cv_{cam}"
wall = time.time()
base = settings.frigate_url.rstrip("/")
evs = json.load(urllib.request.urlopen(f"{base}/api/events?cameras={fid}&limit=3", timeout=12))
fe = evs[0]
box = fe["data"]["box"]
evt = {
    "class_name": "car",
    "bbox": {"x": box[0], "y": box[1], "width": box[2], "height": box[3]},
    "bbox_ts": wall,
}
matched, delta = engine._correlate_event(fid, wall, evt, camera_id=cam)
print("matched", bool(matched), "delta", round(delta, 2), "offset", round(engine._demo_clock_offset.get(cam, 0), 2))
if matched:
    print("frigate_id", str(matched.get("id", ""))[:24], "start", matched.get("start_time"))
