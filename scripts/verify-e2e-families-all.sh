#!/usr/bin/env bash
# Lance toutes les familles E2E + matrice + tests conseillés
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAIL=0
run() {
  echo ""
  echo ">>> $1"
  if bash "$2"; then echo "[PASS] $1"; else echo "[FAIL] $1"; FAIL=$((FAIL + 1)); fi
}

echo "╔══════════════════════════════════════════════════╗"
echo "║  CitéVision — Lot E2E par famille + matrice      ║"
echo "╚══════════════════════════════════════════════════╝"

bash "$ROOT/fix-sh-lf.sh" 2>/dev/null || true

run "Spatial" "$ROOT/verify-e2e-family-spatial.sh"
run "Identité" "$ROOT/verify-e2e-family-identity.sh"
run "Routier" "$ROOT/verify-e2e-family-road.sh"
run "SEQUENCE theft" "$ROOT/verify-e2e-sequence-theft.sh"
run "Templates ex-Bientôt (10)" "$ROOT/verify-e2e-bientot-templates.sh"
run "Webhook CloudEvents" "$ROOT/verify-e2e-webhook-cloudevents.sh"
run "Pytest catalogue Disponibles" "$ROOT/verify-e2e-pytest-catalog.sh"

echo ""
echo ">>> Regénération matrice"
python3 "$ROOT/generate-rule-coverage-matrix.py" || FAIL=$((FAIL + 1))

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "=== LOT E2E FAMILLES OK ==="
  exit 0
fi
echo "=== LOT E2E FAMILLES FAILED ($FAIL) ==="
exit 1
