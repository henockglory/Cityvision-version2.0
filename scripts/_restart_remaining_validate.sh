#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision

# Stop previous remaining run
pkill -f '_validate_remaining' 2>/dev/null || true
pkill -f 'validate_rule_dod' 2>/dev/null || true
pkill -f '_validate_rule_frigate_1hit' 2>/dev/null || true
sleep 2

cp -f "$WIN/scripts/validate_rule_dod.py" "$ROOT/scripts/"
cp -f "$WIN/scripts/_validate_rule_frigate_1hit.py" "$ROOT/scripts/"
cp -f "$WIN/scripts/capture_alerts_ui.mjs" "$ROOT/scripts/"
sed -i 's/\r$//' "$ROOT/scripts/validate_rule_dod.py" \
  "$ROOT/scripts/_validate_rule_frigate_1hit.py" \
  "$ROOT/scripts/capture_alerts_ui.mjs"

bash "$ROOT/scripts/_validate_remaining.sh"
