#!/usr/bin/env python3
"""Sample HSV traffic-light classification on demo Feux video."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError:
    print("opencv/numpy required")
    sys.exit(1)

# Import classifier from ai-engine
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ai-engine" / "src"))
from citevision_ai.road_enforcement.traffic_light import classify_light_color, _polygon_pixel_bbox

VIDEO = Path.home() / "citevision-v2/data/videos/demo/e312f375-7442-4089-8022-ed232abc09e8/d4cadc04-f940-497d-8031-80418ac7dd86_stream.mp4"

# Zone_des_feux polygon from API (normalized) - fetch via psql if needed
POLYGON = None

def main():
    import urllib.request
    API = "http://127.0.0.1:8081"
    login = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{API}/api/v1/auth/login",
        data=json.dumps({"email": "glory.henock@hologram.cd", "password": "Hologram2026!"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )).read())
    token = login["access_token"]
    zones = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{API}/api/v1/orgs/e312f375-7442-4089-8022-ed232abc09e8/zones",
        headers={"Authorization": f"Bearer {token}"},
    )).read())
    poly = None
    for z in zones:
        if z.get("name") == "Zone_des_feux":
            p = z.get("polygon")
            if isinstance(p, str):
                p = json.loads(p)
            poly = p
            break
    if not poly:
        print("Zone_des_feux polygon not found")
        return
    if not VIDEO.exists():
        print(f"Video missing: {VIDEO}")
        return
    cap = cv2.VideoCapture(str(VIDEO))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    box = _polygon_pixel_bbox(poly, w, h)
    print(f"Video {w}x{h}, ROI box={box}, polygon points={len(poly)}")
    if not box:
        print("Invalid ROI bbox")
        return
    x1, y1, x2, y2 = box
    counts = {}
    for i in range(0, min(300, int(cap.get(cv2.CAP_PROP_FRAME_COUNT))), 5):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = cap.read()
        if not ok:
            break
        state, ratios = classify_light_color(frame[y1:y2, x1:x2])
        counts[state] = counts.get(state, 0) + 1
        if i < 30 or state == "red":
            print(f"  frame {i}: {state} ratios={{{', '.join(f'{k}:{v:.3f}' for k,v in ratios.items())}}}")
    print("Summary over sampled frames:", counts)

if __name__ == "__main__":
    main()
