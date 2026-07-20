#!/usr/bin/env bash
set -euo pipefail
ROOT=~/citevision-v2
cd "$ROOT"
echo "=== outer log (latest) ==="
ls -lt logs/demo-five-rules-gated-manual-*.outer.log 2>/dev/null | head -3
OUTER=$(ls -t logs/demo-five-rules-gated-manual-*.outer.log 2>/dev/null | head -1 || true)
if [ -n "${OUTER:-}" ]; then
  echo "FILE=$OUTER"
  cat "$OUTER"
fi
echo ""
echo "=== processes ==="
pgrep -af '_run_five_rules_gated|validate_demo_five_rules' || echo NO_PROC
echo ""
echo "=== recent gated logs ==="
ls -lt logs/demo-five-rules-gated*.log 2>/dev/null | head -8
