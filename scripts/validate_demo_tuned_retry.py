#!/usr/bin/env python3
"""Re-run E2E for tuned rules (feu, vitesse, téléphone) — 10 min max each, stop at 2 hits."""
from __future__ import annotations

import os
import sys

# Only the three rules that failed after default spatial tuning.
os.environ.setdefault("RULE_TIMEOUT_SEC", "600")
os.environ.setdefault("TARGET_DETECTIONS", "2")
os.environ.setdefault(
    "RULES_ONLY",
    "Démo · Feu rouge,Démo · Excès de vitesse,Démo · Téléphone au volant",
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import validate_demo_five_rules as v  # noqa: E402

NAMES = {n.strip() for n in os.environ["RULES_ONLY"].split(",") if n.strip()}
v.RULES = [r for r in v.RULES if r["name"] in NAMES]

if __name__ == "__main__":
    if len(v.RULES) != len(NAMES):
        missing = NAMES - {r["name"] for r in v.RULES}
        print(f"WARN: unknown rule names: {missing}", file=sys.stderr)
    raise SystemExit(v.main())
