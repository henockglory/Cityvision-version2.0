#!/usr/bin/env bash
# Test 45: end-to-end 1-hit feu (PASS_1HIT only).
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
source scripts/microtest/_microtest_common.sh

GATE_FEU="${GATE_FEU:-NO-GO}"
GATE_GEMINI="${GATE_GEMINI_FEU:-NO-GO}"
if [ "$GATE_FEU" != "GO" ] && [ "${MICROTEST_FORCE_1HIT:-0}" != "1" ]; then
  echo "ABORT test 45: GATE_FEU=$GATE_FEU (set MICROTEST_FORCE_1HIT=1 to override)"
  exit 2
fi

patch_env_kv
restart_ai || exit 1
# Ensure rules-engine for 1-hit tests
RE_PORT="${RULES_ENGINE_PORT:-8010}"
if ! curl -sf -m 3 "http://127.0.0.1:${RE_PORT}/health" >/dev/null 2>&1; then
  bash scripts/_start-rules-engine.sh 2>/dev/null || true
  sleep 5
fi
pkill -f '_validate_rule_frigate_1hit' 2>/dev/null || true
pkill -f '_observe_1hit_blockers' 2>/dev/null || true
sleep 1

export RULE_NAME='Démo · Feu rouge'
export RULE_ALIAS=feu
export MAX_WAIT_SEC="${MAX_WAIT_SEC:-720}"
export RULE_DURATION_SEC="${RULE_DURATION_SEC:-720}"
export FRIGATE_MAX_ALIGN_MS=45000

TS=$(microtest_ts)
LOG="$ROOT/logs/microtest-1hit-feu-${TS}.log"
archive_blockers "1hit-feu-before" >/dev/null

bash scripts/_tmp_rerun_one_rule.sh 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}
archive_blockers "1hit-feu-after" >/dev/null

REPORT="${MICROTEST_REPORT:-$ROOT/logs/microtest-report-${TS}.md}"
append_report "$REPORT" "Test 45 1-hit feu" "rc=$RC log=$LOG PASS_1HIT_criteria=alert+frigate_track"
echo "TEST45_RC=$RC"
exit "$RC"
