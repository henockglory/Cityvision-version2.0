#!/usr/bin/env bash
# Tests 36-40: orchestration / chaos / disk.
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
source scripts/microtest/_microtest_common.sh
REPORT="${MICROTEST_REPORT:-$ROOT/logs/microtest-report-$(microtest_ts).md}"

archive_blockers "orch-before" | tee -a "$REPORT"

# Test 39 disk
DF=$(df -h /mnt/c | tail -1)
append_report "$REPORT" "Test 39 disk" "$DF"

# Test 38 chaos frigate restart (optional)
if [ "${MICROTEST_CHAOS_FRIGATE:-1}" = "1" ]; then
  T0=$(date +%s)
  docker restart citevision-v2-frigate 2>/dev/null || true
  for i in $(seq 1 40); do
    curl -sf -m 3 http://127.0.0.1:5000/api/version >/dev/null 2>&1 && break
    sleep 3
  done
  T1=$(date +%s)
  append_report "$REPORT" "Test 38 frigate chaos" "recovery_sec=$((T1-T0))"
fi

archive_blockers "orch-after" | tee -a "$REPORT"
echo "orchestration done"
