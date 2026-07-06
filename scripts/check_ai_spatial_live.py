#!/usr/bin/env python3
"""Verify AI pipeline spatial behaviors and offline traffic-light detection."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai-engine" / "src"))

API = "http://127.0.0.1:8081"
AI = "http://127.0.0.1:8001"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
FEUX = "726ff8a1-8442-4bdb-96ad-ec40a2fbb424"
LIGNE = "01ee632c-271c-4e66-ba98-3d1d7e430c09"
EMAIL = "glory.henock@hologram.cd"
PASS = "Hologram2026!"


def req(method: str, url: str, body: dict | None = None, token: str | None = None) -> object:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as resp:
        return json.loads(resp.read().decode())


def ai_spatial(camera_id: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{AI}/cameras/{camera_id}/spatial", timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(f"  AI spatial {camera_id[:8]}: HTTP {exc.code}")
        return None


def zones_for_camera(token: str, camera_id: str) -> list[dict]:
    zones = req("GET", f"{API}/api/v1/orgs/{ORG}/zones", token=token)
    if isinstance(zones, dict):
        zones = zones.get("items", zones)
    out: list[dict] = []
    for z in zones or []:
        if z.get("camera_id") != camera_id:
            continue
        bc = z.get("behavior_config") or {}
        if isinstance(bc, str):
            bc = json.loads(bc) if bc.startswith("{") else {}
        out.append(
            {
                "name": z.get("name"),
                "behavior": bc.get("behavior", z.get("zone_kind", "")),
                "behavior_config": bc.get("config", {}),
                "polygon": z.get("polygon") or [],
            }
        )
    return out


def offline_traffic_light(zlist: list[dict]) -> set[str]:
    try:
        import cv2
    except ImportError:
        print("  offline TL: opencv missing")
        return set()

    from citevision_ai.road_enforcement.traffic_light import TrafficLightEngine

    video = (
        Path.home()
        / "citevision-v2/data/videos/demo/e312f375-7442-4089-8022-ed232abc09e8/d4cadc04-f940-497d-8031-80418ac7dd86_stream.mp4"
    )
    if not video.exists():
        print(f"  offline TL: video missing {video}")
        return set()

    cap = cv2.VideoCapture(str(video))
    engine = TrafficLightEngine()
    states: set[str] = set()
    for _ in range(400):
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        for evt in engine.process_frame(FEUX, frame, [], "2026-01-01T00:00:00Z", zlist):
            if evt.get("event_type") == "traffic_light_state":
                meta = evt.get("metadata") or {}
                states.add(str(meta.get("state", "")))
    cap.release()
    return states


def main() -> int:
    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    token = login["access_token"]

    print("=== AI live spatial ===")
    for cid, label in ((FEUX, "Feux"), (LIGNE, "Ligne Continue")):
        live = ai_spatial(cid)
        if live:
            print(f"  {label}: zones={live.get('zone_count')} behaviors={live.get('behaviors')}")

    print("\n=== DB zones (expected behaviors) ===")
    feux_z = zones_for_camera(token, FEUX)
    ligne_z = zones_for_camera(token, LIGNE)
    print(f"  Feux: {[(z['name'], z['behavior']) for z in feux_z]}")
    print(f"  Ligne: {[(z['name'], z['behavior']) for z in ligne_z]}")

    print("\n=== Offline traffic-light simulation ===")
    states = offline_traffic_light(feux_z)
    print(f"  states seen: {sorted(states) or '(none)'}")

    live = ai_spatial(FEUX)
    if live and "traffic_light_color" not in (live.get("behaviors") or []):
        print("\n[FAIL] AI pipeline missing traffic_light_color — run force-spatial-reload.sh")
        return 1
    if not states:
        print("\n[WARN] Offline simulation saw no traffic_light_state (HSV/zone ROI issue)")
        return 2
    print("\n[OK] Spatial + offline TL check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
