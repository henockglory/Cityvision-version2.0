#!/usr/bin/env bash
# Tests 1-10: Feu / HSV gate diagnostics.
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
source scripts/microtest/_microtest_common.sh

DUR="${MICROTEST_HSV_SEC:-300}"
INTERVAL="${MICROTEST_POLL_SEC:-5}"
REPORT="${MICROTEST_REPORT:-$ROOT/logs/microtest-report-$(microtest_ts).md}"
CSV="${MICROTEST_CSV:-$ROOT/logs/microtest-feu-hsv-$(microtest_ts).csv}"
mkdir -p "$(dirname "$CSV")"
: > "$REPORT"
echo "# Micro-test feu/HSV $(microtest_ts)" >> "$REPORT"

echo "test,wall,raw,stable,gate,grace_active,red_enqueued,skipped_not_red" > "$CSV"
BEFORE="$(fetch_blockers)"
archive_blockers "feu-before" >/dev/null
B0=$(bridge_stat red_light_enqueued "$BEFORE")
S0=$(bridge_stat red_light_skipped_not_red "$BEFORE")

echo "Polling ${DUR}s interval ${INTERVAL}s -> $CSV"
end=$(( $(date +%s) + DUR ))
n=0
while [ "$(date +%s)" -lt "$end" ]; do
  n=$((n+1))
  B="$(fetch_blockers)"
  python3 - <<PY >> "$CSV"
import json, urllib.request, time
AI="$AI"
n=$n
try:
  d=json.loads(urllib.request.urlopen(AI+"/debug/rule-blockers", timeout=10).read())
except Exception:
  d={}
gd=(d.get("hsv_gate_debug") or {})
row=gd[list(gd.keys())[0]] if gd else {}
fb=d.get("frigate_bridge") or {}
print(f"{n},{time.time()},{row.get('raw','')},{row.get('stable','')},{row.get('gate','')},{row.get('grace_active','')},{fb.get('red_light_enqueued',0)},{fb.get('red_light_skipped_not_red',0)}")
PY
  sleep "$INTERVAL"
done

AFTER="$(fetch_blockers)"
archive_blockers "feu-after" >/dev/null
B1=$(bridge_stat red_light_enqueued "$AFTER")
S1=$(bridge_stat red_light_skipped_not_red "$AFTER")
DELTA=$((B1-B0))

# Test 3 variant: raw gate (optional, restore after)
if [ "${MICROTEST_RUN_RAW_GATE:-0}" = "1" ]; then
  python3 - <<'PY'
from pathlib import Path
p=Path.home()/ "citevision-v2"/ ".env"
t=p.read_text(encoding="utf-8").replace("RED_LIGHT_GATE_MODE=or","RED_LIGHT_GATE_MODE=raw")
p.write_text(t, encoding="utf-8")
PY
  restart_ai || true
  sleep 60
  RAW_AFTER="$(fetch_blockers)"
  RAW_ENQ=$(bridge_stat red_light_enqueued "$RAW_AFTER")
  append_report "$REPORT" "Test 3 raw gate" "enqueued=$RAW_ENQ (compare to or=$B1)"
  patch_env_kv; restart_ai || true
fi

# Test 8 zone_miss
ZM=$(grep -r "zone_miss" "$ROOT/logs" 2>/dev/null | wc -l || echo 0)

append_report "$REPORT" "Tests 1-2 baseline" "delta_enqueued=$DELTA before=$B0 after=$B1 skipped_not_red_delta=$((S1-S0)) csv=$CSV"
append_report "$REPORT" "Test 8 zone_miss" "grep_count=$ZM"

GATE="NO-GO"
if [ "$DELTA" -ge 3 ]; then GATE="GO"; fi
echo "GATE_FEU=$GATE delta_enqueued=$DELTA" | tee -a "$REPORT"
echo "$REPORT"
echo "$CSV"
