#!/usr/bin/env python3
"""Baseline metrics before/after Frigate integration (read-only)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _docker_psql(sql: str) -> str:
    cmd = [
        "docker", "exec", "citevision-v2-postgres",
        "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return r.stdout.strip() if r.returncode == 0 else ""


def main() -> int:
    out: dict = {"ts": datetime.now(timezone.utc).isoformat(), "metrics": {}}
    partial = _docker_psql(
        "SELECT COUNT(*) FROM alerts WHERE metadata->>'evidence_status' = 'partial';"
    )
    total = _docker_psql(
        "SELECT COUNT(*) FROM alerts WHERE metadata->>'evidence_status' IS NOT NULL;"
    )
    out["metrics"]["alerts_partial"] = int(partial or 0)
    out["metrics"]["alerts_with_evidence_status"] = int(total or 0)
    cam108 = _docker_psql(
        "SELECT COUNT(*) FROM cameras WHERE host::text LIKE '%108%';"
    )
    out["metrics"]["cameras_108"] = int(cam108 or 0)
    frigate_url = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000")
    try:
        import urllib.request

        with urllib.request.urlopen(f"{frigate_url.rstrip('/')}/api/version", timeout=5) as resp:
            out["frigate"] = {"reachable": True, "body": resp.read().decode()[:200]}
    except Exception as exc:
        out["frigate"] = {"reachable": False, "error": str(exc)}
    path = ROOT / "scripts" / "frigate-baseline.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
