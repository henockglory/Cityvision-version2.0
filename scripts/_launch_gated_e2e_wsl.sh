#!/usr/bin/env bash
# Launch gated five-rules E2E (background-safe).
set -euo pipefail
ROOT=~/citevision-v2
cd "$ROOT"
sed -i 's/\r$//' scripts/_run_five_rules_gated.sh scripts/validate_demo_five_rules.py 2>/dev/null || true
mkdir -p logs
export DEMO_MODE=1
export DEMO_EVIDENCE_BACKEND=strict_frigate
export DEMO_RESOLUTION=1080p
export LIVE_108_ENABLED=0
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Hologram2026!}"
STAMP=$(date +%Y%m%d-%H%M%S)
OUTER="logs/demo-five-rules-gated-manual-${STAMP}.outer.log"
nohup bash scripts/_run_five_rules_gated.sh >"$OUTER" 2>&1 &
PID=$!
echo "PID=$PID"
echo "OUTER=$OUTER"
sleep 3
if kill -0 "$PID" 2>/dev/null; then
  echo "STATUS=running"
else
  echo "STATUS=exited_early"
  tail -50 "$OUTER" || true
fi
