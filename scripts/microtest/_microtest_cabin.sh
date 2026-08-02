#!/usr/bin/env bash
# Tests 20-25: cabin Gemini (after Q18 gate).
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
source scripts/microtest/_microtest_common.sh
REPORT="${MICROTEST_REPORT:-$ROOT/logs/microtest-report-$(microtest_ts).md}"

Q18_VERDICT="${CABIN_Q18_VERDICT:-unknown}"
if [ "$Q18_VERDICT" = "freeze" ] || [ "$Q18_VERDICT" = "lt30" ]; then
  append_report "$REPORT" "Tests 19-25" "SKIP cabin freeze Q18 verdict=$Q18_VERDICT"
  echo "SKIP cabin tests Q18=$Q18_VERDICT"
  exit 0
fi

BEFORE="$(fetch_blockers)"
B0=$(bridge_stat cabin_enqueued "$BEFORE")
U0=$(vlm_stat unclear "$BEFORE")

# Test 22: note phone rule contention (manual disable via UI if needed)
append_report "$REPORT" "Test 22" "phone_contention=manual_check_is_enabled"

sleep "${MICROTEST_CABIN_SEC:-120}"
AFTER="$(fetch_blockers)"
B1=$(bridge_stat cabin_enqueued "$AFTER")
U1=$(vlm_stat unclear "$AFTER")
E1=$(vlm_stat emitted "$AFTER")
DF=$(vlm_stat dropped_full "$AFTER")

append_report "$REPORT" "Tests 20-25 cabin poll" "cabin_enqueued_delta=$((B1-B0)) unclear_delta=$((U1-U0)) emitted=$E1 dropped_full=$DF"
echo "cabin_enqueued_delta=$((B1-B0)) emitted=$E1"
