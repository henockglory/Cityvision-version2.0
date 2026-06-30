#!/usr/bin/env bash
set -euo pipefail
WIN="/mnt/c/Users/gheno/citevision"
WSL="$HOME/citevision-v2"
cp "$WIN/backend/internal/alerts/service.go" "$WSL/backend/internal/alerts/"
cp "$WIN/rules-engine/internal/actions/executor.go" "$WSL/rules-engine/internal/actions/"
cp "$WIN/scripts/validate-demo-feux-only.sh" "$WSL/scripts/"
cp "$WIN/scripts/validate_demo_five_rules.py" "$WSL/scripts/"
python3 "$WSL/scripts/fix-crlf.py" "$WSL/scripts/validate-demo-feux-only.sh"
cd "$WSL"
export RULE_TIMEOUT_SEC=600 TARGET_DETECTIONS=2 PYTHONUNBUFFERED=1
bash scripts/validate-demo-feux-only.sh 2>&1 | tee logs/demo-feux-retest.log
