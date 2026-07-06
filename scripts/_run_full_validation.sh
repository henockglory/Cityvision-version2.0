#!/usr/bin/env bash
# Full Phase A E2E — 5/5 rules, speed included ([A.2], [N.116]).
set -euo pipefail
export ADMIN_EMAIL="${ADMIN_EMAIL:-glory.henock@hologram.cd}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Henockglory@03}"
export TARGET_DETECTIONS="${TARGET_DETECTIONS:-2}"
export RULE_TIMEOUT_SEC="${RULE_TIMEOUT_SEC:-600}"
export DEMO_SETTLE_SEC="${DEMO_SETTLE_SEC:-40}"
export RULE_SYNC_WAIT_SEC="${RULE_SYNC_WAIT_SEC:-35}"
export SPEED_DEFERRED=0
export REPORT_TAG=final
unset VALIDATE_ONLY

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs

echo "== [N.116] validate_demo 5/5 START $(date -u +%H:%M:%S) =="
python3 -u scripts/validate_demo_five_rules.py
rc=$?
echo "== validate_demo END rc=$rc =="

python3 scripts/generate-roadmap-138-status.py
python3 scripts/audit-charter-138.py
exit "$rc"
