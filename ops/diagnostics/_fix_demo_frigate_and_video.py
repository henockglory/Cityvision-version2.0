#!/usr/bin/env python3
"""Diagnose + fix demo: activate video stream, rebuild Frigate, resync ingest."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request

API = "http://127.0.0.1:8081"
EMAIL = "glory.henock@hologram.cd"
PASS = "Henockglory@03"
INTERNAL = None

# Demo videos by rule (org 74d51ead...)
VIDEOS = {
    "feux": "aaea7c30-1c4c-4ce5-9cd6-4b1f8ded4118",
    "ceinture": "f046692c-d830-4431-b8ec-8bc509eab00a",
    "ligne": "e774ae7a-137c-4c2f-901a-7324bb64c8b2",
    "comptage": "1a7dd0c0-1557-427c-9a9e-03da850561d9",
}


def req(method: str, url: str, token: str | None = None, body: dict | None = None) -> object:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if INTERNAL and "/internal/" in url:
        headers["X-Internal-Key"] = INTERNAL
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=120) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def load_internal_key() -> str:
    import os
    for p in ("/home/gheno/citevision-v2/.env",):
        if not os.path.exists(p):
            continue
        for line in open(p, encoding="utf-8"):
            if line.startswith("INTERNAL_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    return "changeme_internal_service_key"


def psql(sql: str) -> str:
    return subprocess.check_output(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        text=True,
    ).strip()


def main() -> int:
    global INTERNAL
    INTERNAL = load_internal_key()
    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    token = login["access_token"]
    me = req("GET", f"{API}/api/v1/auth/me", token=token)
    org = me["org_id"]
    print(f"org={org}")

    # Activate feux video for UI preview + ingest
    vid = VIDEOS["feux"]
    req("PATCH", f"{API}/api/v1/orgs/{org}/demo/settings", token=token, body={
        "active_video_id": vid,
        "active_camera_id": None,
        "source_mode": "video",
    })
    print(f"activated video {vid[:8]} (Feux)")

    req("POST", f"{API}/api/v1/internal/demo/repair-streams", body={})
    print("repair-streams OK")
    req("POST", f"{API}/api/v1/internal/ingest/frigate/rebuild", body={})
    print("frigate rebuild OK")

    subprocess.run(["docker", "restart", "citevision-v2-frigate"], check=False)
    time.sleep(18)

    stats = json.loads(urllib.request.urlopen("http://127.0.0.1:5000/api/stats", timeout=10).read())
    cams = stats.get("cameras") or {}
    print(f"frigate cameras active: {len(cams)} detection_fps={stats.get('detection_fps')}")
    if not cams:
        print("WARN: Frigate still safe-mode — check /dev/shm/logs/frigate/current")

    req("POST", f"{API}/api/v1/internal/ingest/resync-spatial", body={})
    print("resync-spatial OK")
    time.sleep(15)

    ai = json.loads(urllib.request.urlopen("http://127.0.0.1:8001/cameras", timeout=10).read())
    running = [c for c in ai.get("cameras", []) if c.get("running")]
    print(f"AI ingest running: {len(running)}")
    for c in running:
        print(f"  {c.get('camera_id','')[:8]} source={c.get('source')} frames={c.get('frames_processed')}")

    row = psql(
        "SELECT payload->>'evidence_status', payload->>'capture_source' "
        "FROM events WHERE event_type IN ('speeding','phone_use_violation','red_light_violation') "
        "ORDER BY ingested_at DESC LIMIT 1;"
    )
    print(f"latest event evidence: {row or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
