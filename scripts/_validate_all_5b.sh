#!/usr/bin/env bash
# Re-validate all 5 with cabin live-source fix. Log to validate-all-5b.
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
LOG="$ROOT/logs/validate-all-5b.log"
{
  echo "=== validate-all-5b start $(date -Is) ==="
  bash scripts/health_check_all.sh || exit 1
  for alias in phone seatbelt speeding red_light counting; do
    echo
    echo "########## VALIDATE $alias $(date -Is) ##########"
    export RULE_DURATION_SEC="${RULE_DURATION_SEC:-480}"
    export VALIDATE_MODE=wait
    bash scripts/validate_rule.sh "$alias" || echo "VALIDATE_EXIT=$? alias=$alias"
    echo "########## DONE $alias $(date -Is) ##########"
  done
  echo
  echo "=== artefacts ==="
  find validation-evidence -name report.json | sort | while read -r f; do
    python3 -c "import json;d=json.load(open('$f'));print('$f', d.get('result'), d.get('alias',''))"
  done
  echo "=== validate-all-5b end $(date -Is) ==="
} 2>&1 | tee "$LOG"
