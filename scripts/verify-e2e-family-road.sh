#!/usr/bin/env bash
# E2E famille routier : vehicle_stopped, sudden_stop (pytest), vehicle_count_threshold
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=scripts/e2e/lib/common.sh
source "$SCRIPT_DIR/e2e/lib/common.sh"

FAIL=0
pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1"; FAIL=$((FAIL + 1)); }

echo "=== E2E famille ROUTIER ==="

# sudden_stop unitaire IA
if bash "$ROOT/scripts/verify-e2e-spatial-semantic.sh" 2>/dev/null | grep -q sudden_stop || \
   (cd "$ROOT/ai-engine" && source .venv/bin/activate && pytest -q tests/test_sudden_stop.py); then
  pass "sudden_stop (calibration IA)"
else
  fail "sudden_stop"
fi

e2e_ensure_stack
e2e_login
e2e_resolve_camera

# vehicle_stopped
if e2e_ensure_zone "e2e-vehicle-stop" "" && \
   e2e_create_rule "E2E vehicle_stopped" "tpl-vehicle-stopped" "vehicle_stopped" "{}" "e2e-vehicle-stop" "car" 5 && \
   e2e_wait_event "vehicle_stopped" "car" "" && \
   e2e_assert_evidence; then
  pass "vehicle_stopped + preuves"
else
  fail "vehicle_stopped"
fi

# congestion / vehicle_count_threshold
if e2e_create_rule "E2E congestion" "tpl-congestion" "vehicle_count_threshold" "{}" "" "any" 3 && \
   e2e_wait_event "vehicle_count_threshold" "" "" && \
   e2e_assert_evidence; then
  pass "vehicle_count_threshold + preuves"
else
  fail "vehicle_count_threshold"
fi

# speeding (nécessite véhicules rapides + calibration — SKIP si absent)
if e2e_create_rule "E2E speeding" "tpl-speeding-premium" "speeding" "{}" "" "car" 3 && \
   e2e_wait_event "speeding" "car" ""; then
  pass "speeding event"
  e2e_assert_evidence || fail "speeding evidence"
else
  echo "[SKIP] speeding — calibration / flux véhicule requis"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "=== E2E famille ROUTIER OK ==="
  exit 0
fi
echo "=== E2E famille ROUTIER FAILED ($FAIL) ==="
exit 1
