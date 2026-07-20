#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2
OUTER=$(ls -t logs/demo-five-rules-gated-manual-*.outer.log 2>/dev/null | head -1)
echo "OUTER=$OUTER mtime=$(stat -c %y "$OUTER" 2>/dev/null | cut -d. -f1)"
pgrep -af '_run_five_rules_gated|validate_demo_five_rules' || echo NO_PROC
echo "--- OUTER key lines ---"
grep -E 'ÉTAPE|PREFLIGHT|PASS|FAIL|PARTIAL|VALIDATION|Frigate|active_rules|=== Démo|HTTPError|Log:' "$OUTER" | tail -50
# newest inner log after outer start
echo "--- INNER candidates ---"
ls -lt logs/demo-five-rules-gated-2*.log 2>/dev/null | head -5
INNER=$(ls -t logs/demo-five-rules-gated-2*.log 2>/dev/null | head -1 || true)
if [ -n "${INNER:-}" ]; then
  echo "INNER=$INNER"
  grep -E 'PREFLIGHT|PASS|FAIL|PARTIAL|SKIPPED|VALIDATION|=== Démo|active_rules|evidence:' "$INNER" | tail -40
fi
