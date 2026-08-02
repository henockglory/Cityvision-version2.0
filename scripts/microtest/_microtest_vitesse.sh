#!/usr/bin/env bash
# Tests 26-30: speed bridge diagnostics.
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
source scripts/microtest/_microtest_common.sh
REPORT="${MICROTEST_REPORT:-$ROOT/logs/microtest-report-$(microtest_ts).md}"

B="$(fetch_blockers)"
EM=$(bridge_stat speed_emitted "$B")
BL=$(bridge_stat speed_below_limit "$B")
SH=$(bridge_stat speed_shadow_max "$B")
append_report "$REPORT" "Test 26-27 blockers" "speed_emitted=$EM speed_below_limit=$BL"

# Test 28 shadow max-in-zone
export FRIGATE_SPEED_EMIT_MODE=shadow_max
python3 - <<'PY'
from pathlib import Path
p=Path.home()/ "citevision-v2"/ ".env"
t=p.read_text(encoding="utf-8")
if "FRIGATE_SPEED_EMIT_MODE=" in t:
    lines=[l if not l.startswith("FRIGATE_SPEED_EMIT_MODE=") else "FRIGATE_SPEED_EMIT_MODE=shadow_max" for l in t.splitlines()]
else:
    lines=t.splitlines()+["FRIGATE_SPEED_EMIT_MODE=shadow_max"]
p.write_text("\n".join(lines)+"\n", encoding="utf-8")
PY
restart_ai || true
sleep "${MICROTEST_SPEED_SHADOW_SEC:-90}"
AF="$(fetch_blockers)"
SH1=$(bridge_stat speed_shadow_max "$AF")
append_report "$REPORT" "Test 28 shadow_max" "speed_shadow_max=$SH1"
patch_env_kv; restart_ai || true

# Test 29 optional 1-hit vitesse (short window if MICROTEST_VITESSE_1HIT=1)
if [ "${MICROTEST_VITESSE_1HIT:-0}" = "1" ]; then
  export RULE_NAME='Démo · Excès de vitesse'
  export RULE_ALIAS=vitesse
  export MAX_WAIT_SEC="${MICROTEST_VITESSE_WAIT:-300}"
  bash scripts/_tmp_rerun_one_rule.sh | tee "$ROOT/logs/microtest-vitesse-1hit.log" || true
  append_report "$REPORT" "Test 29 vitesse 1-hit" "see logs/microtest-vitesse-1hit.log"
fi

echo "speed_emitted=$EM shadow_max=$SH1"
