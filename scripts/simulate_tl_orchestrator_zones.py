#!/usr/bin/env python3
"""Simulate traffic-light pipeline using orchestrator spatial payload."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai-engine" / "src"))

import cv2

from citevision_ai.road_enforcement.traffic_light import TrafficLightEngine

API = "http://127.0.0.1:8081"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
FEUX = "726ff8a1-8442-4bdb-96ad-ec40a2fbb424"
KEY = os.environ.get("INTERNAL_API_KEY", "dev-internal-key-change-me")
VIDEO = (
    Path.home()
    / "citevision-v2/data/videos/demo/e312f375-7442-4089-8022-ed232abc09e8/d4cadc04-f940-497d-8031-80418ac7dd86_stream.mp4"
)


def main() -> None:
    req = urllib.request.Request(
        f"{API}/api/v1/internal/ingest/orgs/{ORG}/cameras/{FEUX}/spatial-config",
        headers={"X-Internal-Key": KEY},
    )
    cfg = json.loads(urllib.request.urlopen(req, timeout=30).read())
    zones = cfg.get("zones") or []
    print("orchestrator behaviors:", [z.get("behavior") for z in zones])
    for z in zones:
        poly = z.get("polygon") or []
        print(f"  {z.get('name')}: polygon points={len(poly)} sample={poly[:1]}")

    cap = cv2.VideoCapture(str(VIDEO))
    engine = TrafficLightEngine()
    state_events = 0
    violation_events = 0
    for _ in range(500):
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        evts = engine.process_frame(FEUX, frame, [], "2026-01-01T00:00:00Z", zones)
        for e in evts:
            et = e.get("event_type")
            if et == "traffic_light_state":
                state_events += 1
            elif et == "red_light_violation":
                violation_events += 1
    cap.release()
    print(f"offline with orchestrator zones: state_events={state_events} violations={violation_events}")


if __name__ == "__main__":
    main()
