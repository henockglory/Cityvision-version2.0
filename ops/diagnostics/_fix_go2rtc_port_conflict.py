#!/usr/bin/env python3
"""Fix go2rtc/Frigate port conflict and repair demo RTSP chain."""
from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path("/home/gheno/citevision-v2")
ENV = ROOT / ".env"
INTERNAL = "changeme_internal_service_key"


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"')
    return env


def post(path: str) -> str:
    req = urllib.request.Request(
        f"http://127.0.0.1:8081{path}",
        data=b"",
        method="POST",
        headers={"X-Internal-Key": INTERNAL},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read().decode()


def main() -> int:
    env = load_env()
    print("GO2RTC_URL=", env.get("GO2RTC_URL"))
    print("FRIGATE_GO2RTC_PORT=", env.get("FRIGATE_GO2RTC_PORT", "(default 8554)"))

    print("\n1) Restart go2rtc docker (reclaim 1984/8554 after Frigate moves)")
    subprocess.run(["docker", "compose", "-f", str(ROOT / "infra" / "docker-compose.yml"), "up", "-d", "go2rtc"], check=False)

    print("2) Restart Frigate (embedded go2rtc -> 1985/8557)")
    subprocess.run(["docker", "restart", "citevision-v2-frigate"], check=False)
    time.sleep(20)

    print("3) repair-streams + frigate rebuild")
    print(post("/api/v1/internal/demo/repair-streams"))
    print(post("/api/v1/internal/ingest/frigate/rebuild"))

    subprocess.run(["docker", "restart", "citevision-v2-frigate"], check=False)
    time.sleep(20)

    print("\n4) Port ownership")
    subprocess.run(["sudo", "lsof", "-i", ":1984", "-i", ":8554", "-i", ":1985", "-i", ":8557"], check=False)

    print("\n5) RTSP test (docker go2rtc demo feux)")
    r = subprocess.run(
        ["timeout", "6", "ffprobe", "-v", "error", "-show_entries", "stream=codec_name",
         "-of", "csv=p=0", "rtsp://127.0.0.1:8554/demo-74d51ead-aaea7c30"],
        capture_output=True, text=True,
    )
    print("ffprobe:", r.stdout.strip() or r.stderr.strip()[:300])

    stats = json.loads(urllib.request.urlopen("http://127.0.0.1:5000/api/stats", timeout=10).read())
    for k, v in sorted((stats.get("cameras") or {}).items()):
        if k.startswith("cv_"):
            print(k, "camera_fps=", v.get("camera_fps"), "det=", v.get("detection_fps"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
