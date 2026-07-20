#!/usr/bin/env python3
"""Global report after 1 km/h limit test on camera 108."""
from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAM108 = "37c7d7fa-12dc-450c-8c4b-ab63ed43a819"
ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
MARKER = "2026-07-08 07:04:41+00"
API = "http://127.0.0.1:8081"
AI = "http://127.0.0.1:8001"
INTERNAL = "changeme_internal_service_key"


def load_env() -> None:
    for p in (ROOT / ".env", Path.home() / "citevision-v2" / ".env"):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
        break


load_env()
INTERNAL = os.environ.get("INTERNAL_API_KEY", INTERNAL)


def psql(sql: str) -> str:
    proc = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", sql],
        capture_output=True,
        text=True,
    )
    return proc.stdout or proc.stderr


def get(url: str, headers: dict | None = None) -> dict:
    r = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(r, timeout=20) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    print("=== CONFIG (limite 1 km/h) ===")
    spatial = get(
        f"{API}/api/v1/internal/ingest/orgs/{ORG}/cameras/{CAM108}/spatial-config",
        {"X-Internal-Key": INTERNAL},
    )
    for z in spatial.get("zones", []):
        if z.get("behavior") == "speed_measurement":
            cfg = z.get("behavior_config") or {}
            print(json.dumps({"zone": z.get("zone_id"), "speed_limit_kmh": cfg.get("speed_limit_kmh"), "live_traffic": cfg.get("live_traffic")}, indent=2))

    print("\n=== NOUVEAUX ÉVÉNEMENTS speeding (depuis limite 1 km/h) ===")
    print(psql(
        f"SELECT occurred_at, payload->>'speed_kmh' as speed, payload->>'bbox_ts' as bbox_ts, "
        f"payload->'metadata'->>'speed_limit_kmh' as limit_meta "
        f"FROM events WHERE camera_id='{CAM108}' AND event_type='speeding' "
        f"AND occurred_at > '{MARKER}' ORDER BY occurred_at DESC LIMIT 10;"
    ))

    print("\n=== ALERTES liées (depuis marker) ===")
    print(psql(
        f"SELECT a.created_at, a.title, e.payload->>'speed_kmh' as speed "
        f"FROM alerts a JOIN events e ON e.id=a.event_id "
        f"WHERE e.camera_id='{CAM108}' AND e.event_type='speeding' AND a.created_at > '{MARKER}' "
        f"ORDER BY a.created_at DESC LIMIT 10;"
    ))

    print("\n=== INGEST caméra 108 ===")
    cams = get(f"{AI}/cameras")
    cam = next(c for c in cams["cameras"] if c["camera_id"] == CAM108)
    print(json.dumps(cam, indent=2))

    print("\n=== GPU health ===")
    print(json.dumps(get(f"{AI}/health/gpu"), indent=2))

    print("\n=== AUDIT ===")
    proc = subprocess.run(
        [str(Path.home() / "citevision-v2/ai-engine/.venv/bin/python3"), str(ROOT / "scripts/audit_live_speed_camera.py")],
        cwd=str(Path.home() / "citevision-v2"),
        capture_output=True,
        text=True,
    )
    print(proc.stdout)


if __name__ == "__main__":
    main()
