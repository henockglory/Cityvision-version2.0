#!/usr/bin/env python3
"""Repair demo streams, smoke-test comptage, run speed/phone/red validation."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

API = "http://127.0.0.1:8081"
AI = "http://127.0.0.1:8001"
INTERNAL = "changeme_internal_service_key"
EMAIL = "glory.henock@hologram.cd"
PASS = "Henockglory@03"
COMPT_CAM = "9a3cd323-3820-46f0-aa5b-86c086a4a782"
COMPT_VIDEO = "1a7dd0c0-1557-427c-9a9e-03da850561d9"
ROOT = "/home/gheno/citevision-v2"


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


def login() -> tuple[str, str]:
    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    token = login["access_token"]
    me = req("GET", f"{API}/api/v1/auth/me", token)
    return token, me["org_id"]


def line_car_total(token: str, org: str) -> int:
    ctr = req("GET", f"{API}/api/v1/orgs/{org}/lines/counters?camera_id={COMPT_CAM}", token)
    car = [c for c in ctr if c.get("class_filter") == "car"]
    return int(car[0]["count_total"]) if car else 0


def ai_cameras() -> list[dict]:
    return req("GET", f"{AI}/cameras").get("cameras", [])


def go2rtc_streams() -> list[str]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:1984/api/streams", timeout=5) as r:
            return list(json.loads(r.read().decode()).keys())
    except Exception:
        return []


def wait_health(url: str, attempts: int = 30) -> None:
    for _ in range(attempts):
        try:
            urllib.request.urlopen(url, timeout=3)
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError(f"health timeout: {url}")


def main() -> int:
    print("=== bootstrap stack ===")
    subprocess.run([sys.executable, f"{ROOT}/scripts/_restart_frigate_demo.py"], check=True)
    wait_health(f"{API}/health")
    wait_health(f"{AI}/health")

    token, org = login()
    print("=== repair demo streams ===")
    repair = req("POST", f"{API}/api/v1/internal/demo/repair-streams", internal=True)
    print(repair)
    streams = [s for s in go2rtc_streams() if s.startswith("demo-")]
    print(f"go2rtc demo streams: {streams}")

    print("\n=== comptage smoke test ===")
    baseline = line_car_total(token, org)
    print(f"car counter baseline={baseline}")
    req("PATCH", f"{API}/api/v1/orgs/{org}/demo/settings", token, {"active_video_id": COMPT_VIDEO})
    print(f"active video -> {COMPT_VIDEO}")
    req("POST", f"{API}/api/v1/internal/ingest/resync-spatial", internal=True)
    time.sleep(50)
    cams = ai_cameras()
    compt = [c for c in cams if c.get("camera_id") == COMPT_CAM]
    print(f"ai cameras running: {[c.get('camera_id') for c in cams if c.get('running')]}")
    if compt:
        print(f"comptage worker: {compt[0]}")
    else:
        print("WARN: comptage worker not running")

    deadline = time.time() + 120
    moved = False
    while time.time() < deadline:
        now = line_car_total(token, org)
        if now > baseline:
            print(f"OK counter moved {baseline} -> {now}")
            moved = True
            break
        time.sleep(10)
        print(f"  waiting counter... still {now}")
    if not moved:
        print("FAIL comptage counter did not increment in 120s")

    print("\n=== validation speed / phone / red light ===")
    env = os.environ.copy()
    env["TARGET_DETECTIONS"] = env.get("TARGET_DETECTIONS", "1")
    env["RULE_TIMEOUT_SEC"] = env.get("RULE_TIMEOUT_SEC", "420")
    env["RULE_SYNC_WAIT_SEC"] = env.get("RULE_SYNC_WAIT_SEC", "45")
    env["VALIDATE_ONLY"] = "Démo · Excès de vitesse,Démo · Téléphone au volant,Démo · Feu rouge"
    proc = subprocess.run(
        [sys.executable, f"{ROOT}/scripts/validate_demo_five_rules.py"],
        env=env,
        cwd=ROOT,
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
