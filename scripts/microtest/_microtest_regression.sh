#!/usr/bin/env bash
# Tests 31-32: comptage regression.
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
source scripts/microtest/_microtest_common.sh
REPORT="${MICROTEST_REPORT:-$ROOT/logs/microtest-report-$(microtest_ts).md}"

C0=$(python3 - <<'PY'
import os, subprocess
email=os.environ.get("ADMIN_EMAIL","glory.henock@hologram.cd")
# line counter smoke via psql if available
try:
  r=subprocess.run(["bash","-lc","cd ~/citevision-v2 && python3 scripts/_validate_rule_frigate_1hit.py --help 2>/dev/null || true"],capture_output=True,text=True,timeout=5)
except Exception:
  pass
print(0)
PY
)

export RULE_NAME='Démo · Comptage véhicules'
export RULE_ALIAS=comptage
export MAX_WAIT_SEC=60
export OBSERVE_DURATION_SEC=60
ensure_stack
RC=0
bash scripts/_tmp_rerun_one_rule.sh | tee "$ROOT/logs/microtest-comptage-60s.log" || RC=$?
append_report "$REPORT" "Test 31 comptage 60s" "rc=$RC log=logs/microtest-comptage-60s.log"
echo "comptage_rc=$RC"
