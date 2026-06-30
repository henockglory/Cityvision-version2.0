#!/usr/bin/env python3
"""Compare orchestrator vs API spatial and offline TL on Feux video."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai-engine" / "src"))

import cv2

API = "http://127.0.0.1:8081"
AI = "http://127.0.0.1:8001"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
FEUX = "726ff8a1-8442-4bdb-96ad-ec40a2fbb424"
KEY = "changeme_internal_service_key"
EMAIL = "glory.henock@hologram.cd"
PASS = "Hologram2026!"
VIDEO = (
    Path.home()
    / "citevision-v2/data/videos/demo/e312f375-7442-4089-8022-ed232abc09e8"
    / "d4cadc04-f940-497d-8031-80418ac7dd86_stream.mp4"
)


def req(method: str, url: str, body: dict | None = None, headers: dict | None = None) -> object:
    h = {"Content-Type": "application/json", **(headers or {})}
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(request, timeout=60) as resp:
        return json.loads(resp.read().decode())


def api_zones(token: str) -> list[dict]:
    zones = req("GET", f"{API}/api/v1/orgs/{ORG}/zones", headers={"Authorization": f"Bearer {token}"})
    if isinstance(zones, dict):
        zones = zones.get("items", zones)
    out = []
    for z in zones or []:
        if z.get("camera_id") != FEUX:
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


def orch_zones() -> list[dict]:
    data = req(
        "GET",
        f"{API}/api/v1/internal/ingest/orgs/{ORG}/cameras/{FEUX}/spatial-config",
        headers={"X-Internal-Key": KEY},
    )
    return data.get("zones") or []


def simulate(zlist: list[dict], label: str) -> None:
    from citevision_ai.road_enforcement.traffic_light import TrafficLightEngine

    cap = cv2.VideoCapture(str(VIDEO))
    engine = TrafficLightEngine()
    states: set[str] = set()
    for _ in range(400):
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        for evt in engine.process_frame(FEUX, frame, [], "2026-01-01T00:00:00Z", zlist):
            if evt.get("event_type") == "traffic_light_state":
                states.add(str((evt.get("metadata") or {}).get("state")))
    cap.release()
    print(f"  {label}: {sorted(states) or '(none)'}")


def main() -> None:
    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    token = login["access_token"]
    api = api_zones(token)
    orch = orch_zones()
    print("API zones:", [(z["name"], z["behavior"], len(z["polygon"])) for z in api])
    print("Orch zones:", [(z.get("name"), z.get("behavior"), len(z.get("polygon") or [])) for z in orch])
    simulate(api, "API zones offline")
    simulate(orch, "Orch zones offline")


if __name__ == "__main__":
    main()
