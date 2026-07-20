#!/usr/bin/env python3
"""Compare offline TL vs live pipeline spatial on one Feux frame."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai-engine" / "src"))

import cv2

AI = "http://127.0.0.1:8001"
FEUX = "726ff8a1-8442-4bdb-96ad-ec40a2fbb424"
VIDEO = (
    Path.home()
    / "citevision-v2/data/videos/demo/e312f375-7442-4089-8022-ed232abc09e8"
    / "d4cadc04-f940-497d-8031-80418ac7dd86_stream.mp4"
)


def fetch_spatial() -> dict:
    with urllib.request.urlopen(f"{AI}/cameras/{FEUX}/spatial", timeout=10) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    from citevision_ai.road_enforcement.traffic_light import TrafficLightEngine

    spatial = fetch_spatial()
    print("AI spatial:", spatial)

    # Rebuild zone list like pipeline (need full zone dicts with polygons)
    with urllib.request.urlopen(
        f"http://127.0.0.1:8081/api/v1/internal/ingest/orgs/e312f375-7442-4089-8022-ed232abc09e8/cameras/{FEUX}/spatial-config",
        headers={"X-Internal-Key": "dev-internal-key-change-me"},
    ) as resp:
        orch = json.loads(resp.read().decode())

    zones = orch.get("zones") or []
    print("Orchestrator behaviors:", [z.get("behavior") for z in zones])

    cap = cv2.VideoCapture(str(VIDEO))
    engine = TrafficLightEngine()
    states: set[str] = set()
    for i in range(200):
        ok, frame = cap.read()
        if not ok:
            break
        for evt in engine.process_frame(FEUX, frame, [], "2026-01-01T00:00:00Z", zones):
            if evt.get("event_type") == "traffic_light_state":
                states.add(str((evt.get("metadata") or {}).get("state")))
    cap.release()
    print("Offline orch zones states:", sorted(states))


if __name__ == "__main__":
    main()
