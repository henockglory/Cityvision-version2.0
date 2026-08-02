#!/usr/bin/env bash
# Master runner: micro-tests 1-45 with gates and report.
set -uo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
export PYTHON="${ROOT}/ai-engine/.venv/bin/python"
export PATH="${ROOT}/ai-engine/.venv/bin:${PATH}"
TS=$(date -u +%Y%m%dT%H%M%SZ)
export MICROTEST_REPORT="$ROOT/logs/microtest-report-${TS}.md"
export MICROTEST_CSV="$ROOT/logs/microtest-feu-hsv-${TS}.csv"

source scripts/microtest/_microtest_common.sh
export MICROTEST_REPORT MICROTEST_CSV

{
  echo "# Micro-test campaign report $TS"
  echo "PASS level: PASS_1HIT only (not PASS_DoD)"
  echo ""
} > "$MICROTEST_REPORT"

echo "=== Phase 0: sync env + smoke ==="
patch_env_kv
ensure_stack
restart_ai || { echo "AI restart failed"; exit 1; }
smoke_stack | tee -a "$MICROTEST_REPORT"

PY="$(microtest_python)"

echo "=== Phase A: feu HSV 1-10 ==="
# Shortened poll for campaign if MICROTEST_FAST=1
export MICROTEST_HSV_SEC="${MICROTEST_HSV_SEC:-120}"
export MICROTEST_POLL_SEC="${MICROTEST_POLL_SEC:-5}"
bash scripts/microtest/_microtest_feu_hsv.sh | tee "$ROOT/logs/microtest-feu-run.log"
GATE_FEU=$(grep -o 'GATE_FEU=[A-Z-]*' "$ROOT/logs/microtest-feu-run.log" | tail -1 | cut -d= -f2 || echo NO-GO)
export GATE_FEU
append_report "$MICROTEST_REPORT" "Gate A feu" "GATE_FEU=$GATE_FEU"

echo "=== Phase B: Q18 cabin dump ==="
"$PY" scripts/microtest/_microtest_dump_cabin.py | tee "$ROOT/logs/microtest-cabin-dump.log"
# Auto Q18 verdict from manifest heuristic
export CABIN_Q18_VERDICT=$("$PY" - <<'PY'
import json
from pathlib import Path
root=Path.home()/ "citevision-v2"/ "validation-evidence"
dirs=sorted(root.glob("cabin-dump-*"))
if not dirs:
  print("unknown"); raise SystemExit
m=json.loads((dirs[-1]/ "manifest.json").read_text())
items=m.get("items") or []
if not items:
  print("freeze"); raise SystemExit
big=sum(1 for i in items if int(i.get("bytes") or 0) >= 8000)
ratio=big/len(items)
if ratio >= 0.5:
  print("ge50")
elif ratio >= 0.3:
  print("30-49")
else:
  print("freeze")
PY
)
append_report "$MICROTEST_REPORT" "Gate B Q18 auto" "CABIN_Q18_VERDICT=$CABIN_Q18_VERDICT (human review recommended)"

echo "=== Phase C: Gemini feu 11-18 ==="
"$PY" scripts/microtest/_microtest_dump_feu_roi.py 2>/dev/null || true
export GEMINI_TEST_DIR="$(ls -dt "$ROOT"/validation-evidence/feu-roi-* 2>/dev/null | head -1 || true)"
"$PY" scripts/microtest/_microtest_gemini_feux.py | tee "$ROOT/logs/microtest-gemini-feux.log" || true
GATE_GEMINI=$(grep -o 'GATE_GEMINI_FEU=[A-Z-]*' "$ROOT/logs/microtest-gemini-feux.log" | tail -1 | cut -d= -f2 || echo NO-GO)
export GATE_GEMINI_FEU="$GATE_GEMINI"
append_report "$MICROTEST_REPORT" "Gate C Gemini feu" "GATE_GEMINI_FEU=$GATE_GEMINI"

if [ "$CABIN_Q18_VERDICT" != "freeze" ] && [ "$CABIN_Q18_VERDICT" != "lt30" ]; then
  echo "=== Phase C2: cabin 19-25 ==="
  export CABIN_Q18_VERDICT
  bash scripts/microtest/_microtest_cabin.sh || true
else
  append_report "$MICROTEST_REPORT" "Cabin 19-25" "SKIP frozen Q18=$CABIN_Q18_VERDICT"
fi

echo "=== Phase D: vitesse 26-30 ==="
bash scripts/microtest/_microtest_vitesse.sh || true

echo "=== Phase D2: regression 31-32 ==="
bash scripts/microtest/_microtest_regression.sh || true

echo "=== Phase E: evidence 33-35 ==="
bash scripts/microtest/_microtest_evidence.sh || true

echo "=== Phase E2: orchestration 36-40 ==="
bash scripts/microtest/_microtest_orchestration.sh || true

echo "=== Phase E3: synergy 41-44 ==="
bash scripts/microtest/_microtest_synergy.sh || true

echo "=== Phase F: test 45 1-hit feu ==="
export GATE_FEU GATE_GEMINI_FEU MICROTEST_REPORT
# Allow 1-hit when gates fail but document override
export MICROTEST_FORCE_1HIT="${MICROTEST_FORCE_1HIT:-1}"
bash scripts/microtest/_microtest_1hit_feu.sh | tee "$ROOT/logs/microtest-test45.log" || true
T45=$(grep -o 'TEST45_RC=[0-9]*' "$ROOT/logs/microtest-test45.log" | tail -1 | cut -d= -f2 || echo 1)

WIN_REPORT="/mnt/c/Users/gheno/citevision/docs/MICROTEST-REPORT-${TS}.md"
cp -f "$MICROTEST_REPORT" "$WIN_REPORT" 2>/dev/null || true

{
  echo ""
  echo "## Summary"
  echo "- GATE_FEU: $GATE_FEU"
  echo "- GATE_GEMINI_FEU: $GATE_GEMINI"
  echo "- CABIN_Q18: $CABIN_Q18_VERDICT"
  echo "- TEST45_RC: $T45"
  echo "- SECURITY: rotate Gemini API key if exposed in chat"
} >> "$MICROTEST_REPORT"
cp -f "$MICROTEST_REPORT" "$WIN_REPORT" 2>/dev/null || true

echo "DONE report=$MICROTEST_REPORT"
echo "WIN=$WIN_REPORT"
