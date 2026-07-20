#!/usr/bin/env python3
"""Restart backend with .env, rebuild Frigate (incl. demo cameras), restart AI."""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path("/home/gheno/citevision-v2")
ENV_FILE = ROOT / ".env"
INTERNAL_KEY = "changeme_internal_service_key"


def load_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = "/usr/local/go/bin:/usr/bin:/bin:" + env.get("PATH", "")
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            env[key.strip()] = val.strip()
    return env


def run(cmd: list[str], env: dict[str, str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd or ROOT, env=env, check=True)


def pkill(pattern: str) -> None:
    subprocess.run(["pkill", "-f", pattern], capture_output=True)


def stop_backend() -> None:
    for pat in (
        "citevision-api",
        "go run ./cmd/api",
        "/tmp/go-build",
        "b001/exe/api",
        "/mnt/c/Citevision/backend/bin/citevision-api",
    ):
        pkill(pat)
    time.sleep(3)


def wait_health(url: str, attempts: int = 20) -> dict:
    for i in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:
            print(f"  waiting {url} ({exc})")
            time.sleep(2)
    raise RuntimeError(f"timeout: {url}")


def main() -> None:
    env = load_env()
    stop_backend()

    run(
        ["go", "build", "-o", "bin/citevision-api", "./cmd/api"],
        env,
        cwd=ROOT / "backend",
    )

    log = ROOT / "logs" / "backend.log"
    proc = subprocess.Popen(
        [str(ROOT / "backend" / "bin" / "citevision-api")],
        cwd=ROOT,
        env=env,
        stdout=log.open("a"),
        stderr=subprocess.STDOUT,
    )
    (ROOT / "logs" / "backend.pid").write_text(str(proc.pid), encoding="utf-8")
    print(f"backend pid={proc.pid}")
    wait_health("http://127.0.0.1:8081/health")

    frigate_health = wait_health("http://127.0.0.1:8081/health/frigate")
    print("frigate health:", json.dumps(frigate_health, indent=2))

    req = urllib.request.Request(
        "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild",
        data=b"",
        method="POST",
        headers={"X-Internal-Key": INTERNAL_KEY},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        print("frigate rebuild:", resp.read().decode())

    cfg = ROOT / "infra" / "frigate-config" / "config.yml"
    text = cfg.read_text(encoding="utf-8")
    demo_cams = [ln for ln in text.splitlines() if "demo-" in ln or "Démo" in ln]
    print(f"config cameras lines with demo: {len(demo_cams)}")
    for ln in demo_cams[:8]:
        print(" ", ln.strip())

    subprocess.run(["docker", "restart", "citevision-v2-frigate"], env=env, check=False)
    time.sleep(15)

    # Restart AI via project script (CUDA venv + run-ai-engine.sh)
    subprocess.run(["python3", str(ROOT / "scripts" / "_restart_ai.py")], env=env, check=True)
    print("[OK] stack ready for demo Frigate tests")


if __name__ == "__main__":
    main()
