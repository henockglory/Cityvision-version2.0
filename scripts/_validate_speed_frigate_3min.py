#!/usr/bin/env python3
"""Validation ciblée vitesse 3 min — ingest + Frigate evidence."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
INTERNAL = os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")
ORG = os.environ.get("DEMO_ORG_ID", "74d51ead-97a7-4e41-a488-503a9b90c466")
SPEED_VID = "e774ae7a-137c-4c2f-901a-7324bb64c8b2"
SPEED_CAM = "55694d53-8f58-4981-91b2-7c6cd528a25d"
SPEED_RULE = "Démo · Excès de vitesse"
DURATION = int(os.environ.get("RULE_DURATION_SEC", "180"))


def req(method: str, url: str, token: str | None = None, body: dict | None = None, internal: bool = False):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if internal:
        headers["X-Internal-Key"] = INTERNAL
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=120) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def psql(sql: str) -> str:
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True, check=False,
    )
    return (r.stdout or "").strip()


def ai_health() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=5) as r:
            return json.loads(r.read()).get("status") == "ok"
    except Exception:
        return False


def camera_status(cam_id: str) -> dict:
    if not ai_health():
        return {"last_error": "ai_down"}
    try:
        data = req("GET", "http://127.0.0.1:8001/cameras")
        for c in data.get("cameras", []):
            if c.get("camera_id") == cam_id:
                return c
    except Exception as exc:
        return {"last_error": str(exc)}
    return {"last_error": "camera_not_registered"}


def wait_frigate_events(frigate_cam: str, sec: int = 90) -> int:
    """Wait until Frigate lists at least one recent event for the demo camera."""
    import urllib.parse
    import urllib.request

    base = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000").rstrip("/")
    qs = urllib.parse.urlencode({"cameras": frigate_cam, "limit": 5})
    url = f"{base}/api/events?{qs}"
    deadline = time.time() + sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=8) as resp:
                events = json.loads(resp.read().decode())
            n = len(events) if isinstance(events, list) else 0
            print(f"  frigate events={n} cam={frigate_cam[:16]}", flush=True)
            if n >= 1:
                return n
        except Exception as exc:
            print(f"  frigate poll err={exc}", flush=True)
        time.sleep(8)
    return 0


def wait_ingest(cam_id: str, sec: int = 120) -> dict:
    deadline = time.time() + sec
    last: dict = {}
    while time.time() < deadline:
        if not ai_health():
            print("  AI down — restart required", flush=True)
            time.sleep(5)
            continue
        last = camera_status(cam_id)
        fp = int(last.get("frames_processed") or 0)
        print(f"  ingest processed={fp} read={last.get('frames_read')} err={last.get('last_error')}", flush=True)
        if fp >= 6:
            return last
        try:
            req("POST", f"{API}/api/v1/internal/ingest/resync-spatial", internal=True)
        except Exception:
            pass
        time.sleep(10)
    return last


def main() -> int:
    print("=== Validation vitesse 3 min (Frigate evidence) ===", flush=True)
    if not ai_health():
        print("[FAIL] AI not running — run: python3 scripts/_restart_ai.py", flush=True)
        return 1

    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    tok = login["access_token"]
    rules = req("GET", f"{API}/api/v1/orgs/{ORG}/rules", tok)
    speed = next((r for r in rules if r.get("name") == SPEED_RULE), None)
    if not speed:
        print("[FAIL] speed rule missing", flush=True)
        return 1

    for r in rules:
        if str(r.get("name", "")).startswith("Démo"):
            req("PATCH", f"{API}/api/v1/orgs/{ORG}/rules/{r['id']}", tok, {"is_enabled": False})
    time.sleep(3)

    req("PATCH", f"{API}/api/v1/orgs/{ORG}/demo/settings", tok, {
        "source_mode": "video", "active_video_id": SPEED_VID, "active_camera_id": None,
    })
    print("speed video active", flush=True)

    frigate_cam = f"cv_{SPEED_CAM}"
    if wait_frigate_events(frigate_cam, 90) < 1:
        print("[WARN] no Frigate events yet — continuing anyway", flush=True)

    st = wait_ingest(SPEED_CAM, 120)
    if int(st.get("frames_processed") or 0) < 6:
        print("[FAIL] ingest not ready", flush=True)
        return 1

    since = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S%z").replace("+0000", "+00")
    req("PATCH", f"{API}/api/v1/orgs/{ORG}/rules/{speed['id']}", tok, {"is_enabled": True})
    print(f"rule enabled — {DURATION}s window", flush=True)

    deadline = time.time() + DURATION
    while time.time() < deadline:
        time.sleep(20)
        if not ai_health():
            print("  WARN AI down during window", flush=True)

    evt = psql(
        f"SELECT count(*) FROM events e JOIN cameras c ON c.id=e.camera_id "
        f"WHERE c.org_id='{ORG}'::uuid AND e.event_type='speeding' AND e.ingested_at>='{since}'::timestamptz;"
    )
    alerts = psql(
        f"SELECT count(*) FROM alerts a "
        f"WHERE a.org_id='{ORG}'::uuid AND a.rule_id='{speed['id']}'::uuid "
        f"AND a.created_at>='{since}'::timestamptz;"
    )
    frigate = psql(
        f"SELECT count(*) FROM alerts a "
        f"WHERE a.org_id='{ORG}'::uuid AND a.rule_id='{speed['id']}'::uuid "
        f"AND a.created_at>='{since}'::timestamptz "
        f"AND a.evidence_snapshot->'package'->'metadata'->>'capture_source'='frigate_track';"
    )
    req("PATCH", f"{API}/api/v1/orgs/{ORG}/rules/{speed['id']}", tok, {"is_enabled": False})

    print(f"events={evt} alerts={alerts} frigate_track={frigate}", flush=True)
    status = "PASS" if int(evt or 0) >= 1 and int(alerts or 0) >= 1 and int(frigate or 0) >= 1 else "PARTIAL" if int(evt or 0) >= 1 else "FAIL"
    print(f"RESULT: {status}", flush=True)
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
