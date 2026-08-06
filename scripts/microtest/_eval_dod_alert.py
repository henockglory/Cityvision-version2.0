#!/usr/bin/env python3
"""Evaluate DoD checks against a specific alert id."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_rule_dod import RULE_CATALOG, evaluate_dod, asset_roles, package_meta  # noqa: E402

aid = sys.argv[1] if len(sys.argv) > 1 else "748002fa-4fa8-46bb-ac43-adabb1972a14"
r = subprocess.run(
    [
        "docker",
        "exec",
        "citevision-v2-postgres",
        "psql",
        "-U",
        "citevision",
        "-d",
        "citevision",
        "-t",
        "-A",
        "-c",
        f"SELECT evidence_snapshot::text FROM alerts WHERE id='{aid}'::uuid;",
    ],
    capture_output=True,
    text=True,
    check=False,
)
raw = (r.stdout or "").strip()
if not raw:
    print("no alert", r.stderr)
    raise SystemExit(1)
snap = json.loads(raw)
alert = {"alert_id": aid, "evidence_snapshot": snap}
cfg = RULE_CATALOG["red_light"]
roles = asset_roles(alert)
meta = package_meta(alert)
print("roles:", list(roles.keys()))
print("meta status:", meta.get("evidence_status"), "plate:", meta.get("plate_number"), "missing:", meta.get("missing_roles"))
checks = evaluate_dod("red_light", cfg, alert)
for c in checks:
    print(f"{c['id']}: {'OK' if c['ok'] else 'FAIL'} — {c['detail']}")
