#!/usr/bin/env python3
"""Validate speed evidence + dedup chain before delivery.

Exit 0 only when unit tests pass and runtime smoke checks succeed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AI_ENGINE = ROOT / "ai-engine"


def run(cmd: list[str], *, cwd: Path | None = None) -> None:
    print(f"[RUN] {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=cwd or ROOT, check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def http_ok(url: str, timeout: float = 5.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError):
        return False


def smoke_runtime() -> None:
    frontend = os.environ.get("FRONTEND_URL", "http://127.0.0.1:5174")
    ai = os.environ.get("AI_HEALTH_URL", "http://127.0.0.1:8001/health")
    backend = os.environ.get("BACKEND_HEALTH_URL", "http://127.0.0.1:8081/health")
    for name, url in [("frontend", frontend), ("AI", ai), ("backend", backend)]:
        if not http_ok(url):
            print(f"[FAIL] {name} not reachable: {url}")
            raise SystemExit(1)
        print(f"[OK] {name} {url}")

    wsl_dest = Path.home() / "citevision-v2"
    form = wsl_dest / "frontend/src/components/evidence/EvidencePolicyForm.tsx"
    if form.exists():
        text = form.read_text(encoding="utf-8")
        if "imageRoles" not in text:
            print("[FAIL] WSL frontend missing imageRoles UI")
            raise SystemExit(1)
        print("[OK] WSL frontend evidence roles UI")


def main() -> None:
    skip_unit = os.environ.get("SKIP_UNIT_TESTS", "").strip() in ("1", "true", "yes")
    skip_smoke = os.environ.get("SKIP_SMOKE", "").strip() in ("1", "true", "yes")
    live_audit = os.environ.get("LIVE_AUDIT", "").strip() in ("1", "true", "yes")

    if not skip_unit:
        py = os.environ.get("AI_VENV_PYTHON", str(AI_ENGINE / ".venv/bin/python3"))
        if not Path(py).exists():
            py = sys.executable
        run([
            py, "-m", "pytest",
            "tests/test_evidence_capture.py",
            "tests/test_zone_speed_evidence.py",
            "tests/test_zone_geometry.py::test_zone_speed_spatial_dedup_same_vehicle_new_track_id",
            "-q",
        ], cwd=AI_ENGINE)
        print("[OK] unit tests")

    if not skip_smoke:
        smoke_runtime()

    if live_audit:
        py = os.environ.get("AI_VENV_PYTHON", str(AI_ENGINE / ".venv/bin/python3"))
        if not Path(py).exists():
            py = sys.executable
        run([py, str(ROOT / "scripts" / "audit_live_speed_camera.py")])

    print("[OK] validate_speed_evidence_chain passed")


if __name__ == "__main__":
    main()
