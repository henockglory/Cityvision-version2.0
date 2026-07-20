#!/usr/bin/env bash
# Sequential live validation — all 5 aliases (A.2). One PASS artefact each.
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
LOG="$ROOT/logs/validate-all-5.log"
mkdir -p "$ROOT/logs" "$ROOT/validation-evidence"
{
  echo "=== validate-all-5 start $(date -Is) ==="
  bash scripts/health_check_all.sh || { echo "HEALTH RED — abort"; exit 1; }
  for alias in speeding red_light phone seatbelt counting; do
    echo
    echo "########## VALIDATE $alias $(date -Is) ##########"
    # Per-rule wait budget (env overrideable)
    export RULE_DURATION_SEC="${RULE_DURATION_SEC:-600}"
    export VALIDATE_MODE=wait
    bash scripts/validate_rule.sh "$alias" || echo "VALIDATE_EXIT=$? alias=$alias"
    echo "########## DONE $alias $(date -Is) ##########"
  done
  echo
  echo "=== artefacts ==="
  find validation-evidence -name report.json | sort | while read -r f; do
    python3 -c "import json;d=json.load(open('$f'));print('$f', d.get('verdict') or d.get('result') or d.get('status'), d.get('alias',''))" 2>/dev/null || echo "$f parse_err"
  done
  echo "=== validate-all-5 end $(date -Is) ==="
} 2>&1 | tee "$LOG"
