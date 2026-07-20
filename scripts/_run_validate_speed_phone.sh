#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOG="$ROOT/logs/validate-speed-phone.log"
: >"$LOG"

RULES=(
  "Démo · Excès de vitesse"
  "Démo · Téléphone au volant"
)
PASS=0
FAIL=0
for RULE in "${RULES[@]}"; do
  echo "=== 1-hit: $RULE ===" | tee -a "$LOG"
  if RULE_NAME="$RULE" RULE_DURATION_SEC=420 python3 -u scripts/_validate_rule_frigate_1hit.py 2>&1 | tee -a "$LOG"; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
  fi
  sleep 10
done
echo "=== SUMMARY pass=$PASS fail=$FAIL (feu rouge déjà OK) ===" | tee -a "$LOG"
exit "$FAIL"
