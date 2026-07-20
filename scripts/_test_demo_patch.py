#!/usr/bin/env python3
import json
import sys
import urllib.request

API = "http://127.0.0.1:8081"
ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
VID = sys.argv[1] if len(sys.argv) > 1 else "aaea7c30-1c4c-4ce5-9cd6-4b1f8ded4118"

login = json.loads(
    urllib.request.urlopen(
        urllib.request.Request(
            f"{API}/api/v1/auth/login",
            data=json.dumps({"email": "glory.henock@hologram.cd", "password": "Hologram2026!"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        ),
        timeout=30,
    ).read()
)
tok = login["access_token"]
req = urllib.request.Request(
    f"{API}/api/v1/orgs/{ORG}/demo/settings",
    data=json.dumps({"source_mode": "video", "active_video_id": VID, "active_camera_id": None}).encode(),
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {tok}"},
    method="PATCH",
)
with urllib.request.urlopen(req, timeout=180) as r:
    raw = r.read().decode()
    body = json.loads(raw)
    print("RAW keys:", list(body.keys()))
    print("pipeline_status=", body.get("pipeline_status"))
    print("ingest_ready=", body.get("ingest_ready"))
    print("active_camera_id=", body.get("active_camera_id"))
