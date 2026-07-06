#!/usr/bin/env python3
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai-engine" / "src"))

from citevision_ai.analytics.zone_speed import ZoneSpeedEngine, _point_in_polygon  # noqa: E402
from citevision_ai.analytics.zone_geometry import resolve_speed_distance_m  # noqa: E402

API = "http://127.0.0.1:8081"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
LIGNE = "01ee632c-271c-4e66-ba98-3d1d7e430c09"


def req(method, url, body=None, token=None):
    headers = {"Content-Type": "application/json"} if body else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read())


def main():
    tok = req("POST", f"{API}/api/v1/auth/login", {"email": "glory.henock@hologram.cd", "password": "Hologram2026!"})["access_token"]
    rows = req("GET", f"{API}/api/v1/orgs/{ORG}/zones", token=tok)
    zlist = []
    for z in rows:
        if z.get("camera_id") != LIGNE:
            continue
        bc = z.get("behavior_config") or {}
        zlist.append({
            "zone_id": z["name"],
            "behavior": "speed_measurement",
            "behavior_config": bc.get("config", {}),
            "polygon": z.get("polygon") or [],
        })
    print("config:", zlist[0]["behavior_config"])
    engine = ZoneSpeedEngine()
    w, h = 1920, 1080
    poly = zlist[0]["polygon"]
    cfg = zlist[0]["behavior_config"]

    def centroid(bbox):
        cx = (float(bbox["x"]) + float(bbox["width"]) / 2) / w
        cy = (float(bbox["y"]) + float(bbox["height"]) * 0.85) / h
        return cx, cy

    track = {"track_id": 99, "class_name": "car", "bbox": {"x": 0.42 * w, "y": 0.10 * h, "width": 0.08 * w, "height": 0.08 * h}}
    c1 = centroid(track["bbox"])
    print("entry inside:", _point_in_polygon(c1[0], c1[1], poly), c1)
    engine.process_frame(LIGNE, [track], zlist, w, h, 1000.0, "2026-01-01T00:00:00Z")
    track2 = {"track_id": 99, "class_name": "car", "bbox": {"x": 0.55 * w, "y": 0.75 * h, "width": 0.10 * w, "height": 0.08 * h}}
    c2 = centroid(track2["bbox"])
    print("exit inside:", _point_in_polygon(c2[0], c2[1], poly), c2)
    dist, method = resolve_speed_distance_m(poly, cfg, c1, c2)
    print("distance:", dist, method)
    if dist:
        print("speed_kmh:", dist / 3.0 * 3.6)
    ev = engine.process_frame(LIGNE, [track2], zlist, w, h, 1003.0, "2026-01-01T00:00:03Z")
    print("events:", len(ev))
    if ev:
        print(json.dumps(ev[0], indent=2))


if __name__ == "__main__":
    main()
