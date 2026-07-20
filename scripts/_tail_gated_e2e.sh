#!/usr/bin/env bash
# Tail progress of gated E2E without blocking.
set -euo pipefail
cd ~/citevision-v2
OUTER=$(ls -t logs/demo-five-rules-gated-manual-*.outer.log 2>/dev/null | head -1 || true)
INNER=$(ls -t logs/demo-five-rules-gated-2*.log 2>/dev/null | head -1 || true)
echo "OUTER=${OUTER:-none}"
echo "INNER=${INNER:-none}"
pgrep -af '_run_five_rules_gated|validate_demo_five_rules' || echo NO_PROC
echo "--- OUTER tail ---"
[ -n "${OUTER:-}" ] && tail -30 "$OUTER" || true
echo "--- INNER progress ---"
if [ -n "${INNER:-}" ]; then
  grep -E 'PREFLIGHT|PASS|FAIL|PARTIAL|SKIPPED|VALIDATION|=== Démo|active_rules' "$INNER" | tail -40 || true
fi
