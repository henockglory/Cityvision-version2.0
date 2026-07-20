#!/usr/bin/env python3
"""Stop cam 108 segment worker and resync spatial → live RTSP (no record gap)."""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

CAM108 = "37c7d7fa-12dc-450c-8c4b-ab63ed43a819"
AI = "http://127.0.0.1:8001"
API = "http://127.0.0.1:8081/api/v1"


def load_key() -> str:
    for p in (Path.home() / "citevision-v2" / ".env",):
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            if "INTERNAL" in line.upper() and "KEY" in line.upper() and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")


def req(method: str, url: str, data: dict | None = None, headers: dict | None = None) -> dict:
    h = headers or {}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        h.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(url, data=body, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    print("stop camera 108 on AI...")
    try:
        print(req("POST", f"{AI}/cameras/{CAM108}/stop"))
    except Exception as e:
        print(f"stop: {e}")
    time.sleep(2)
    print("resync spatial via backend (starts live RTSP worker)...")
    key = load_key()
    r = urllib.request.Request(
        f"{API}/internal/ingest/resync-spatial",
        method="POST",
        headers={"X-Internal-Key": key, "Content-Length": "0"},
        data=b"",
    )
    with urllib.request.urlopen(r, timeout=60) as resp:
        print(resp.read().decode())
    time.sleep(6)
    cams = req("GET", f"{AI}/cameras")
    cam = next((c for c in cams["cameras"] if c["camera_id"] == CAM108), None)
    if not cam:
        print("cam 108 not in AI worker list")
        return
    mode = cam.get("mode", "live_rtsp")
    print(json.dumps(cam, indent=2))
    if mode == "segment_cycle":
        raise SystemExit("FAIL: still segment_cycle — check SEGMENT_MODE_CAMERA_IDS / config.py")
    print("OK: live RTSP mode (no segment gap)")


if __name__ == "__main__":
    main()
