#!/usr/bin/env python3
"""Offline YOLO + spatial engines on demo videos — count violation candidates."""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai-engine" / "src"))

import cv2

API = "http://127.0.0.1:8081"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
EMAIL = "glory.henock@hologram.cd"
PASS = "Hologram2026!"
VIDEOS = Path.home() / "citevision-v2/data/videos/demo" / ORG

CAMS = {
    "feux": ("726ff8a1-8442-4bdb-96ad-ec40a2fbb424", "d4cadc04-f940-497d-8031-80418ac7dd86_stream.mp4"),
    "ligne": ("01ee632c-271c-4e66-ba98-3d1d7e430c09", "eb1d2b8e-6c8d-47c5-82fa-e3c24f0425e5_stream.mp4"),
}


def req(method: str, url: str, body: dict | None = None, token: str | None = None) -> object:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=60) as resp:
        return json.loads(resp.read().decode())


def zones_for(token: str, camera_id: str) -> list[dict]:
    zones = req("GET", f"{API}/api/v1/orgs/{ORG}/zones", token=token)
    if isinstance(zones, dict):
        zones = zones.get("items", zones)
    out = []
    for z in zones or []:
        if z.get("camera_id") != camera_id:
            continue
        bc = z.get("behavior_config") or {}
        if isinstance(bc, str):
            bc = json.loads(bc) if bc.startswith("{") else {}
        out.append(
            {
                "zone_id": str(z.get("id", z.get("name"))),
                "name": z.get("name"),
                "behavior": bc.get("behavior", z.get("zone_kind", "")),
                "behavior_config": bc.get("config", {}),
                "polygon": z.get("polygon") or [],
            }
        )
    return out


def simulate_feux(zlist: list[dict], video: Path, max_frames: int = 600) -> dict[str, int]:
    from citevision_ai.detection.yolo_onnx import YoloOnnxDetector
    from citevision_ai.tracking.byte_tracker import ByteTracker
    from citevision_ai.road_enforcement.traffic_light import TrafficLightEngine

    det = YoloOnnxDetector(device="cpu")
    det.load()
    tracker = ByteTracker(min_hits=1)
    engine = TrafficLightEngine()
    counts: dict[str, int] = {}
    cap = cv2.VideoCapture(str(video))
    t0 = time.monotonic()
    for fi in range(max_frames):
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        h, w = frame.shape[:2]
        profile_w, profile_h = 640, 384
        resized = cv2.resize(frame, (profile_w, profile_h))
        raw = det.detect(resized)
        sx, sy = w / profile_w, h / profile_h
        for d in raw:
            b = d["bbox"]
            b["x"] *= sx
            b["y"] *= sy
            b["width"] *= sx
            b["height"] *= sy
        tracks = tracker.update(raw)
        track_dicts = [
            {
                "track_id": t.track_id,
                "class_name": t.class_name,
                "confidence": t.confidence,
                "bbox": t.bbox,
            }
            for t in tracks
        ]
        now = time.monotonic()
        for evt in engine.process_frame(
            CAMS["feux"][0], frame, track_dicts, "2026-01-01T00:00:00Z", zlist
        ):
            et = str(evt.get("event_type", ""))
            counts[et] = counts.get(et, 0) + 1
    cap.release()
    counts["_elapsed_s"] = int(time.monotonic() - t0)
    return counts


def simulate_ligne(zlist: list[dict], video: Path, max_frames: int = 600) -> dict[str, int]:
    from citevision_ai.detection.yolo_onnx import YoloOnnxDetector
    from citevision_ai.tracking.byte_tracker import ByteTracker
    from citevision_ai.analytics.zone_speed import ZoneSpeedEngine

    det = YoloOnnxDetector(device="cpu")
    det.load()
    tracker = ByteTracker(min_hits=1)
    engine = ZoneSpeedEngine()
    counts: dict[str, int] = {}
    cap = cv2.VideoCapture(str(video))
    t0 = time.monotonic()
    now_ts = time.monotonic()
    for fi in range(max_frames):
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        h, w = frame.shape[:2]
        profile_w, profile_h = 640, 384
        resized = cv2.resize(frame, (profile_w, profile_h))
        raw = det.detect(resized)
        sx, sy = w / profile_w, h / profile_h
        for d in raw:
            b = d["bbox"]
            b["x"] *= sx
            b["y"] *= sy
            b["width"] *= sx
            b["height"] *= sy
        tracks = tracker.update(raw)
        track_dicts = [
            {
                "track_id": t.track_id,
                "class_name": t.class_name,
                "confidence": t.confidence,
                "bbox": t.bbox,
            }
            for t in tracks
        ]
        now_ts = time.monotonic()
        for evt in engine.process_frame(
            CAMS["ligne"][0], track_dicts, zlist, w, h, now_ts, "2026-01-01T00:00:00Z"
        ):
            et = str(evt.get("event_type", ""))
            counts[et] = counts.get(et, 0) + 1
    cap.release()
    counts["_elapsed_s"] = int(time.monotonic() - t0)
    return counts


def main() -> int:
    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    token = login["access_token"]

    feux_id, feux_vid = CAMS["feux"]
    ligne_id, ligne_vid = CAMS["ligne"]
    feux_z = zones_for(token, feux_id)
    ligne_z = zones_for(token, ligne_id)

    print("=== Feux offline (YOLO + traffic light) ===")
    feux_path = VIDEOS / feux_vid
    if feux_path.exists():
        print(simulate_feux(feux_z, feux_path))
    else:
        print("missing", feux_path)

    print("\n=== Ligne Continue offline (YOLO + zone speed) ===")
    ligne_path = VIDEOS / ligne_vid
    if ligne_path.exists():
        print(simulate_ligne(ligne_z, ligne_path))
    else:
        print("missing", ligne_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
