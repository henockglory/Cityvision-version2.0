#!/usr/bin/env python3
"""Rebuild Frigate config (car tracking) and restart Frigate on WSL."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = "/home/gheno/citevision-v2"
KEY = os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)


def main() -> int:
    # Patch env flags
    subprocess.run([sys.executable, f"{ROOT}/scripts/_patch_wsl_frigate_env.py"], check=True)

    # Build backend with updated compiler
    b = run(["bash", "-lc", f"export PATH=/usr/local/go/bin:$PATH; cd {ROOT}/backend && go build -o bin/citevision-api ./cmd/api"])
    if b.returncode != 0:
        print(b.stderr, file=sys.stderr)
        return 1

    # Restart backend
    run(["pkill", "-f", f"{ROOT}/backend/bin/citevision-api"])
    time.sleep(2)
    subprocess.Popen(
        [f"{ROOT}/backend/bin/citevision-api"],
        cwd=ROOT,
        stdout=open(f"{ROOT}/logs/backend.log", "a"),
        stderr=subprocess.STDOUT,
    )
    for _ in range(20):
        time.sleep(1)
        try:
            with urllib.request.urlopen("http://127.0.0.1:8081/health", timeout=2) as r:
                if json.load(r).get("status") == "ok":
                    break
        except Exception:
            pass
    else:
        print("[ERR] backend not healthy", file=sys.stderr)
        return 1

    req = urllib.request.Request(
        "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild",
        data=b"",
        method="POST",
        headers={"X-Internal-Key": KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode()
            print("[rebuild]", body)
    except Exception as exc:
        print(f"[ERR] frigate rebuild: {exc}", file=sys.stderr)
        return 1

    cfg = open(f"{ROOT}/infra/frigate-config/config.yml", encoding="utf-8").read()
    if "cv_d2eb7076" not in cfg:
        print("[ERR] cam 108 missing from frigate config", file=sys.stderr)
        print(cfg[:800])
        return 1
    if "car" not in cfg:
        print("[WARN] car not in config yaml text")

    run(["docker", "restart", "citevision-v2-frigate"])
    print("[OK] frigate restarting — wait 25s")
    time.sleep(25)

    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:5000/api/events?cameras=cv_d2eb7076-c3b3-40fd-9b2c-0d119bb975c9&limit=30",
            timeout=15,
        ) as resp:
            events = json.loads(resp.read().decode())
    except Exception as exc:
        print(f"[ERR] frigate events: {exc}", file=sys.stderr)
        return 1

    labels: dict[str, int] = {}
    for ev in events if isinstance(events, list) else []:
        labels[ev.get("label", "?")] = labels.get(ev.get("label", "?"), 0) + 1
    print("[labels]", labels)
    cars = labels.get("car", 0) + labels.get("truck", 0) + labels.get("motorcycle", 0)
    if cars == 0:
        print("[WARN] no vehicle events yet — wait for traffic then re-check")
        return 2
    print(f"[OK] vehicle events visible ({cars})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
