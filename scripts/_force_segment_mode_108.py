#!/usr/bin/env python3
"""Stop cam 108, resync ingest, verify segment_cycle mode."""
import json
import os
import time
import urllib.request
from pathlib import Path

CAM108 = "37c7d7fa-12dc-450c-8c4b-ab63ed43a819"
AI = "http://127.0.0.1:8001"
API = "http://127.0.0.1:8081"


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
    key = load_key()
    print(f"internal key prefix: {key[:8]}...")
    print("stop camera 108 on AI...")
    try:
        print(req("POST", f"{AI}/cameras/{CAM108}/stop"))
    except Exception as e:
        print(f"stop: {e}")
    time.sleep(2)
    print("resync spatial via backend...")
    try:
        r = urllib.request.Request(
            f"{API}/internal/ingest/resync-spatial",
            method="POST",
            headers={"X-Internal-Key": key, "Content-Length": "0"},
            data=b"",
        )
        with urllib.request.urlopen(r, timeout=30) as resp:
            print(resp.read().decode())
    except Exception as e:
        print(f"resync error: {e}")
    time.sleep(8)
    cams = req("GET", f"{AI}/cameras")
    cam = next(c for c in cams["cameras"] if c["camera_id"] == CAM108)
    print(json.dumps(cam, indent=2))


if __name__ == "__main__":
    main()
