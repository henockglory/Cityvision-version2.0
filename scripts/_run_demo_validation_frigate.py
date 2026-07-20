#!/usr/bin/env python3
"""Ensure WSL backend+AI up, then run demo validation."""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request

ROOT = "/home/gheno/citevision-v2"


def wait(url: str, n: int = 30) -> None:
    for i in range(n):
        try:
            urllib.request.urlopen(url, timeout=3)
            print(f"[OK] {url}")
            return
        except Exception as exc:
            print(f"  wait {url}: {exc}")
            time.sleep(2)
    raise RuntimeError(url)


def main() -> int:
    env = os.environ.copy()
    env["TARGET_DETECTIONS"] = env.get("TARGET_DETECTIONS", "1")
    env["RULE_TIMEOUT_SEC"] = env.get("RULE_TIMEOUT_SEC", "420")
    env["RULE_SYNC_WAIT_SEC"] = env.get("RULE_SYNC_WAIT_SEC", "45")

    subprocess.run([sys.executable, f"{ROOT}/scripts/_restart_frigate_demo.py"], check=True)
    wait("http://127.0.0.1:8081/health")
    wait("http://127.0.0.1:8081/health/frigate")
    wait("http://127.0.0.1:8001/health")

    proc = subprocess.run(
        [sys.executable, f"{ROOT}/scripts/validate_demo_five_rules.py"],
        env=env,
        cwd=ROOT,
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
