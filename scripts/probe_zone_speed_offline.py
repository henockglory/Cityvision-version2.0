#!/usr/bin/env python3
"""Offline zone-speed probe on demo Ligne Continue video."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai-engine" / "src"))

import cv2  # noqa: E402

from citevision_ai.analytics.zone_speed import ZoneSpeedEngine  # noqa: E402
from citevision_ai.detection.yolo_onnx import YoloOnnxDetector  # noqa: E402
from citevision_ai.tracking.bytetrack import ByteTracker  # noqa: E402

API = "http://127.0.0.1:8081"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
LIGNE = "01ee632c-271c-4e66-ba98-3d1d7e430c09"
EMAIL = "glory.henock@hologram.cd"
PASS = "Hologram2026!"


def login() -> str:
    req = urllib.request.Request(
        API + "/api/v1/auth/login",
        data=json.dumps({"email": EMAIL, "password": PASS}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return json.loads(urllib.request.urlopen(req).read())["access_token"]


def zones(token: str) -> list[dict]:
    rows = json.loads(
        urllib.request.urlopen(
            urllib.request.Request(
                f"{API}/api/v1/orgs/{ORG}/zones",
                headers={"Authorization": "Bearer " + token},
            )
        ).read()
    )
    out = []
    for z in rows:
        if z.get("camera_id") != LIGNE:
            continue
        bc = z.get("behavior_config") or {}
        if isinstance(bc, str):
            bc = json.loads(bc)
        out.append(
            {
                "zone_id": z.get("name"),
                "name": z.get("name"),
                "behavior": bc.get("behavior", z.get("zone_kind", "")),
                "behavior_config": bc.get("config", {}),
                "polygon": z.get("polygon") or [],
            }
        )
    return out


def main() -> int:
    token = login()
    zlist = zones(token)
    video = Path(os.environ.get("DEMO_VIDEO_PATH", ""))
    if not video:
        video = (
            Path("/mnt/c/Users/gheno/citevision/data/videos/demo")
            / ORG
            / "eb1d2b8e-6c8d-47c5-82fa-e3c24f0425e5_stream.mp4"
        )
    if not video.exists():
        video = (
            Path.home()
            / "citevision-v2/data/videos/demo/e312f375-7442-4089-8022-ed232abc09e8/eb1d2b8e-6c8d-47c5-82fa-e3c24f0425e5_stream.mp4"
        )
    if not video.exists():
        print("missing video", video)
        return 1
    det = YoloOnnxDetector()
    det.load()
    tracker = ByteTracker(min_hits=1)
    engine = ZoneSpeedEngine()
    cap = cv2.VideoCapture(str(video))
    speeding = 0
    import time

    t0 = time.monotonic()
    for i in range(600):
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        dets = det.detect(frame)
        tracks = tracker.update(dets)
        td = [
            {
                "track_id": t.track_id,
                "class_name": t.class_name,
                "bbox": t.bbox,
            }
            for t in tracks
        ]
        h, w = frame.shape[:2]
        now = time.monotonic() - t0
        evs = engine.process_frame(LIGNE, td, zlist, w, h, now, "2026-01-01T00:00:00Z")
        speeding += sum(1 for e in evs if e.get("event_type") == "speeding")
    cap.release()
    print(f"offline speeding events: {speeding}")
    print(f"zones: {[(z['name'], z['behavior'], z['behavior_config']) for z in zlist]}")
    return 0 if speeding > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
