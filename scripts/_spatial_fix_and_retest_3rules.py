#!/usr/bin/env python3
"""Stabilize stack, spatial reload, repair streams, re-test 3 demo rules."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = "/home/gheno/citevision-v2"
API = "http://127.0.0.1:8081"
AI = "http://127.0.0.1:8001"
INTERNAL = "changeme_internal_service_key"


def wait(url: str, n: int = 40) -> None:
    for _ in range(n):
        try:
            urllib.request.urlopen(url, timeout=3)
            print(f"[OK] {url}")
            return
        except Exception as exc:
            print(f"  wait {url}: {exc}")
            time.sleep(2)
    raise RuntimeError(url)


def post_internal(path: str) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        data=b"",
        method="POST",
        headers={"X-Internal-Key": INTERNAL},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode() or "{}")


def main() -> int:
    print("=== 1. ensure API + AI healthy ===")
    try:
        urllib.request.urlopen(f"{API}/health", timeout=3)
        urllib.request.urlopen(f"{AI}/health", timeout=3)
        print("stack already up")
    except Exception:
        subprocess.run([sys.executable, f"{ROOT}/scripts/_restart_frigate_demo.py"], check=True)
        wait(f"{API}/health")
        wait(f"{AI}/health")

    # Keep backend alive without killing this script.
    watch = subprocess.run(
        ["pgrep", "-f", "watch-backend.sh"],
        capture_output=True,
        text=True,
    )
    if watch.returncode != 0:
        subprocess.Popen(
            ["bash", f"{ROOT}/scripts/watch-backend.sh"],
            cwd=ROOT,
            stdout=open(f"{ROOT}/logs/watch-backend.log", "a"),
            stderr=subprocess.STDOUT,
        )
        print("started watch-backend")

    print("\n=== 2. repair demo streams ===")
    print(post_internal("/api/v1/internal/demo/repair-streams"))

    print("\n=== 3. seed + resync spatial ===")
    subprocess.run(["bash", f"{ROOT}/scripts/seed-demo-spatial.sh"], check=True)
    print(post_internal("/api/v1/internal/ingest/resync-spatial"))
    time.sleep(12)

    print("\n=== 4. push spatial to all demo cameras ===")
    subprocess.run([sys.executable, f"{ROOT}/scripts/push_ai_spatial_from_api.py"], check=True)
    time.sleep(8)

    print("\n=== 5. validate speed / phone / red light ===")
    env = os.environ.copy()
    env["TARGET_DETECTIONS"] = "1"
    env["RULE_TIMEOUT_SEC"] = "420"
    env["RULE_SYNC_WAIT_SEC"] = "45"
    env["ADMIN_PASSWORD"] = env.get("ADMIN_PASSWORD", "Henockglory@03")
    env["VALIDATE_ONLY"] = "Démo · Excès de vitesse,Démo · Téléphone au volant,Démo · Feu rouge"
    env["REPORT_TAG"] = "spatial-retest"
    return subprocess.run(
        [sys.executable, f"{ROOT}/scripts/validate_demo_five_rules.py"],
        env=env,
        cwd=ROOT,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
