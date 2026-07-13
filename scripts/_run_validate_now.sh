#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOG="$ROOT/logs/validate-3rules-run.log"
: >"$LOG"

bash scripts/preflight_platform.sh 2>&1 | tee -a "$LOG" || exit 1
python3 scripts/_diag_suppressed_evidence.py 2>&1 | tee -a "$LOG" || true

RULES=(
  "Démo · Feu rouge"
  "Démo · Excès de vitesse"
  "Démo · Téléphone au volant"
)
RUNS="${VALIDATE_CONSECUTIVE_RUNS:-3}"
GRAND_FAIL=0

for RUN in $(seq 1 "$RUNS"); do
  echo "=== CONSECUTIVE RUN $RUN/$RUNS ===" | tee -a "$LOG"
  PASS=0
  FAIL=0
  for RULE in "${RULES[@]}"; do
    echo "=== 1-hit: $RULE ===" | tee -a "$LOG"
    if RULE_NAME="$RULE" RULE_DURATION_SEC=420 python3 -u scripts/_validate_rule_frigate_1hit.py 2>&1 | tee -a "$LOG"; then
      PASS=$((PASS + 1))
    else
      FAIL=$((FAIL + 1))
    fi
    sleep 8
  done
  echo "=== RUN $RUN SUMMARY pass=$PASS fail=$FAIL ===" | tee -a "$LOG"
  if [ "$FAIL" -ne 0 ]; then
    GRAND_FAIL=$((GRAND_FAIL + 1))
  fi
done

echo "=== GRAND SUMMARY failed_runs=$GRAND_FAIL / $RUNS ===" | tee -a "$LOG"
exit "$GRAND_FAIL"
