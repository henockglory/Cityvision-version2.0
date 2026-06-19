#!/usr/bin/env bash
# Batterie finale — plan final_premium_stabilization
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FAIL=0
run() {
  echo ""
  echo ">>> $1"
  if bash "$2"; then
    echo "[PASS] $1"
  else
    echo "[FAIL] $1"
    FAIL=$((FAIL + 1))
  fi
}

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  CitéVision — Final premium stabilization validation     ║"
echo "╚══════════════════════════════════════════════════════════╝"

run "E2E bootstrap (migrations, venv, stack)" "$ROOT/scripts/ensure-e2e-ready.sh"

run "Rules composition" "$ROOT/scripts/verify-rules-composition.sh"
run "Camera onboard" "$ROOT/scripts/verify-camera-onboard.sh"
run "Stream quality" "$ROOT/scripts/verify-stream-quality.sh"
run "Routing rules" "$ROOT/scripts/verify-routing-rules.sh"
run "Pytest catalogue" "$ROOT/scripts/verify-e2e-pytest-catalog.sh"
run "E2E event matrix (MQTT)" "$ROOT/scripts/verify-e2e-event-matrix.sh"
run "E2E families (spatial+identity+road+sequence)" "$ROOT/scripts/verify-e2e-families-all.sh"
run "Evidence quality" "$ROOT/scripts/verify-evidence-quality.sh"
run "Evidence playback" "$ROOT/scripts/verify-evidence-playback.sh"
run "UI premium (Playwright)" "$ROOT/scripts/verify-ui-premium.sh"

echo ""
echo ">>> Final commercial reset (rules off, purge test data)"
if bash "$ROOT/scripts/reset-commercial.sh"; then
  echo "[PASS] reset-commercial"
else
  echo "[FAIL] reset-commercial"
  FAIL=$((FAIL + 1))
fi

echo ""
echo ">>> Restart stack"
if bash "$ROOT/scripts/restart-api-frontend.sh" && bash "$ROOT/scripts/restart-ai-engine.sh"; then
  echo "[PASS] stack restart"
else
  echo "[FAIL] stack restart"
  FAIL=$((FAIL + 1))
fi

echo ""
if (( FAIL > 0 )); then
  echo "VALIDATION FAILED ($FAIL step(s))"
  exit 1
fi
echo "VALIDATION PASSED — handoff ready"
exit 0
