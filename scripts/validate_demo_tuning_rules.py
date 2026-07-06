#!/usr/bin/env python3
"""E2E validation for demo rules needing spatial/evidence tuning (feu, vitesse, téléphone)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# Reuse the full validator; only the rule subset and timeout differ.
os.environ.setdefault("RULE_TIMEOUT_SEC", "600")
os.environ.setdefault("TARGET_DETECTIONS", "2")

import validate_demo_five_rules as v  # noqa: E402

v.RULES = [
    {"name": "Démo · Feu rouge", "event_types": ["red_light_violation"], "mail": True, "counter": False},
    {"name": "Démo · Excès de vitesse", "event_types": ["speeding"], "mail": True, "counter": False},
    {
        "name": "Démo · Téléphone au volant",
        "event_types": ["phone_use_violation", "phone_driving"],
        "mail": True,
        "counter": False,
    },
]

if __name__ == "__main__":
    raise SystemExit(v.main())
