#!/usr/bin/env python3
"""Phase P10 checklist runner — read-only validation helpers for Frigate integration."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ("speeding", "line_cross", "red_light", "phone_use", "seatbelt")


def _curl_json(url: str) -> dict:
    try:
        import urllib.request

        with urllib.request.urlopen(url, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        return {"error": str(exc)}


def main() -> int:
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "flags": {
            "FRIGATE_ENABLED": os.environ.get("FRIGATE_ENABLED", "0"),
            "FRIGATE_LIVE": os.environ.get("FRIGATE_LIVE", "0"),
            "FRIGATE_EVIDENCE": os.environ.get("FRIGATE_EVIDENCE", "0"),
            "EVIDENCE_BACKEND": os.environ.get("EVIDENCE_BACKEND", "ring_buffer"),
        },
        "health": {},
        "rules": {r: {"status": "pending", "notes": "Run live demo validation"} for r in RULES},
    }
    api = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081").rstrip("/")
    report["health"]["backend_frigate"] = _curl_json(f"{api}/health/frigate")
    report["health"]["frigate_api"] = _curl_json(
        os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000").rstrip("/") + "/api/version",
    )
    baseline = ROOT / "scripts" / "frigate-baseline.json"
    if baseline.exists():
        report["baseline"] = json.loads(baseline.read_text(encoding="utf-8"))
    out_path = ROOT / "docs" / "FRIGATE-VALIDATION-REPORT.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    audit = ROOT / "scripts" / "audit_evidence_quality.py"
    if audit.exists():
        subprocess.run([sys.executable, str(audit), "--limit", "10"], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
