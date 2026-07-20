#!/usr/bin/env python3
"""Activate speed demo video and wait for AI ingest frames."""
import json
import sys
import time
import urllib.request

API = "http://127.0.0.1:8081"
ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
VID = "e774ae7a-137c-4c2f-901a-7324bb64c8b2"
CAM = "55694d53-8f58-4981-91b2-7c6cd528a25d"
PASS = "Hologram2026!"


def req(method: str, url: str, token: str | None = None, body: dict | None = None, internal: bool = False):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if internal:
        headers["X-Internal-Key"] = "changeme_internal_service_key"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=60) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def main() -> int:
    login = req("POST", f"{API}/api/v1/auth/login", body={"email": "glory.henock@hologram.cd", "password": PASS})
    tok = login["access_token"]
    req(
        "PATCH",
        f"{API}/api/v1/orgs/{ORG}/demo/settings",
        tok,
        {"source_mode": "video", "active_video_id": VID, "active_camera_id": None},
    )
    print("speed video activated")
    for i in range(12):
        req("POST", f"{API}/api/v1/internal/ingest/resync-spatial", internal=True)
        time.sleep(10)
        cams = req("GET", "http://127.0.0.1:8001/cameras")
        target = None
        for c in cams.get("cameras", []):
            if c.get("camera_id") == CAM:
                target = c
                break
        if target:
            fp = int(target.get("frames_processed") or 0)
            fr = int(target.get("frames_read") or 0)
            print(f"  try {i+1}: processed={fp} read={fr} err={target.get('last_error')} rtsp={target.get('rtsp_url','')[:55]}")
            if fp >= 6:
                print("INGEST_OK")
                return 0
        else:
            ids = [c.get("camera_id", "")[:8] for c in cams.get("cameras", [])]
            print(f"  try {i+1}: cam missing, running={ids}")
    print("INGEST_FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
