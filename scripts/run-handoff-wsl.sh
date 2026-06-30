#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2
export PUBLIC_API_BASE="${PUBLIC_API_BASE:-http://localhost:8081/api/v1}"
export RULE_SYNC_WAIT_SEC="${RULE_SYNC_WAIT_SEC:-35}"
LOG="logs/handoff-run.log"
exec bash scripts/validate-demo-handoff.sh 2>&1 | tee "$LOG"
