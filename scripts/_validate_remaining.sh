#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
LOG="$ROOT/logs/validate-remaining.log"
{
  echo "=== remaining start $(date -Is) ==="
  # Ensure frigate up
  if ! timeout 4 curl -sf http://127.0.0.1:5000/api/version >/dev/null; then
    docker restart citevision-v2-frigate
    for i in $(seq 1 30); do
      timeout 3 curl -sf http://127.0.0.1:5000/api/version >/dev/null && break
      sleep 2
    done
  fi
  bash scripts/health_check_all.sh || exit 1
  for alias in seatbelt speeding red_light counting; do
    echo
    echo "########## VALIDATE $alias $(date -Is) ##########"
    export RULE_DURATION_SEC=420
    export VALIDATE_MODE=wait
    # Frigate rebuild often 502 mid-switch — skip rebuild once config already has cams
    export SKIP_FRIGATE_REBUILD=1
    bash scripts/validate_rule.sh "$alias" || echo "EXIT=$? alias=$alias"
    echo "########## DONE $alias $(date -Is) ##########"
  done
  echo "=== summary artefacts ==="
  find validation-evidence -name report.json | sort | while read -r f; do
    python3 -c "import json;d=json.load(open('$f'));print(d.get('result'), d.get('alias'), '$f')"
  done
  echo "=== remaining end $(date -Is) ==="
} 2>&1 | tee "$LOG"
