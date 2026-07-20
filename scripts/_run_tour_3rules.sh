#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
sed -i 's/\r$//' scripts/_validate_3rules_tour_10min.py
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Hologram2026!}"
export ADMIN_EMAIL="${ADMIN_EMAIL:-glory.henock@hologram.cd}"
LOG="$ROOT/logs/validate-3rules-tour-10min.log"
: >"$LOG"
echo "[start] $(date -Is)" | tee -a "$LOG"
python3 -u scripts/_validate_3rules_tour_10min.py 2>&1 | tee -a "$LOG"
echo "[exit] $(date -Is) code=${PIPESTATUS[0]}" | tee -a "$LOG"
