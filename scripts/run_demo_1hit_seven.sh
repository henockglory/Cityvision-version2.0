#!/usr/bin/env bash
set -uo pipefail
cd ~/citevision-v2
cp /mnt/c/Users/gheno/citevision-v2/scripts/validate_demo_1hit_seven.py scripts/validate_demo_1hit_seven.py
export ADMIN_PASSWORD='Hologram2026!'
export DEMO_ORG_ID='74d51ead-97a7-4e41-a488-503a9b90c466'
export RULE_TIMEOUT_SEC="${RULE_TIMEOUT_SEC:-180}"
export DISABLE_END="${DISABLE_END:-0}"
export REPORT_PATH=/tmp/demo_1hit_report.json
export INTERNAL_API_KEY='changeme_internal_service_key'
export PYTHONUNBUFFERED=1
echo "starting 1-hit timeout=${RULE_TIMEOUT_SEC}s"
timeout $(( RULE_TIMEOUT_SEC * 8 + 120 )) python3 -u scripts/validate_demo_1hit_seven.py | tee /tmp/demo_1hit_run.log
echo EXIT:$?
