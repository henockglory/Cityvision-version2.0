#!/usr/bin/env bash
set -euo pipefail
WIN="/mnt/c/Users/gheno/citevision"
WSL="$HOME/citevision-v2"
for f in \
  backend/internal/alerts/service.go \
  rules-engine/internal/actions/executor.go \
  scripts/validate_demo_five_rules.py \
  scripts/validate-demo-five-sequential.sh; do
  mkdir -p "$(dirname "$WSL/$f")"
  cp "$WIN/$f" "$WSL/$f"
done
python3 "$WSL/scripts/fix-crlf.py" "$WSL/scripts/validate-demo-five-sequential.sh"
cd "$WSL"
export RULE_TIMEOUT_SEC=600 TARGET_DETECTIONS=1 PYTHONUNBUFFERED=1
bash scripts/validate-demo-five-sequential.sh 2>&1 | tee logs/demo-five-sequential-run.log
