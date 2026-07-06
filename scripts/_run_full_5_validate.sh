#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export ADMIN_EMAIL="${ADMIN_EMAIL:-glory.henock@hologram.cd}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Henockglory@03}"
export REPORT_TAG="final"
export SPEED_DEFERRED=0
unset VALIDATE_ONLY
python3 scripts/validate_demo_five_rules.py
