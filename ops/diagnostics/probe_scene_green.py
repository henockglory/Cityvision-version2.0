#!/usr/bin/env python3
"""Diagnose scene_green: download latest Frigate clip and classify light frames."""
from __future__ import annotations

import json
import os
import tempfile
import time
import urllib.request

import cv2
import numpy as np

# Import from runtime tree
import sys
sys.path.insert(0, "/home/gheno/citevision-v2/ai-engine/src")
from citevision_ai.road_enforcement.traffic_light import classify_light_color, _polygon_pixel_bbox


def http_json(url: str):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode())


def main() -> None:
    cam = "cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"
    evs = http_json(f"http://127.0.0.1:5000/api/events?cameras={cam}&limit=3&include_thumbnails=0")
    print("events", len(evs))
    # Get light zone from a recent red_light DB event via postgres
    import subprocess
    sql = """
SELECT payload->'metadata'->'light_zone_polygon' AS poly,
       payload->'metadata'->>'light_state' AS ia_light,
       payload->>'evidence_status' AS st,
       payload->>'abort_reason' AS abort
FROM events
WHERE event_type='red_light_violation'
ORDER BY ingested_at DESC LIMIT 1;
"""
    out = subprocess.check_output(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        text=True,
    )
    print("latest db row:", out.strip()[:500])

    # Also fetch zone from cameras spatial via API if possible
    # Use polygons from zones table
    zsql = """
SELECT name, behavior, left(polygon::text, 200)
FROM zones
WHERE camera_id='8ed20433-57d5-4999-a6ab-0bea028b23a3'
LIMIT 10;
"""
    try:
        print(subprocess.check_output(
            ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", zsql],
            text=True,
        ))
    except Exception as e:
        print("zones query", e)
        print(subprocess.check_output(
            ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c",
             "SELECT column_name FROM information_schema.columns WHERE table_name='zones';"],
            text=True,
        ))

    if not evs:
        return
    eid = evs[0]["id"]
    print("download clip", eid)
    url = f"http://127.0.0.1:5000/api/events/{eid}/clip.mp4"
    with urllib.request.urlopen(url, timeout=30) as r:
        clip = r.read()
    print("clip bytes", len(clip))

    # Get polygon from latest event payload
    poly_sql = """
SELECT payload->'metadata'->'light_zone_polygon'
FROM events WHERE event_type='red_light_violation'
  AND payload->'metadata'->'light_zone_polygon' IS NOT NULL
ORDER BY ingested_at DESC LIMIT 1;
"""
    poly_raw = subprocess.check_output(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", poly_sql],
        text=True,
    ).strip()
    poly = json.loads(poly_raw) if poly_raw else []
    print("poly n=", len(poly), "sample", poly[:2] if poly else None)

    if not poly:
        print("no light poly — abort")
        return

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(clip)
        path = tmp.name
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 10
    counts = {"red": 0, "green": 0, "yellow": 0, "unknown": 0, "other": 0}
    samples = []
    idx = 0
    step = max(1, int(fps / 4))
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            h, w = frame.shape[:2]
            box = _polygon_pixel_bbox(poly, w, h)
            if box:
                x1, y1, x2, y2 = box
                state, scores = classify_light_color(frame[y1:y2, x1:x2])
                counts[state if state in counts else "other"] += 1
                if len(samples) < 8:
                    samples.append((round(idx / fps, 2), state, {k: round(v, 3) for k, v in scores.items()}))
        idx += 1
    cap.release()
    os.unlink(path)
    print("frame_counts", counts, "total_checked", sum(counts.values()))
    print("samples", samples)


if __name__ == "__main__":
    main()
