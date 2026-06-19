#!/usr/bin/env bash
# Batterie complète — commandes utiles du plan industrialisation
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="/usr/local/go/bin:$PATH"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  CitéVision — Batterie validation complète               ║"
echo "╚══════════════════════════════════════════════════════════╝"

bash "$ROOT/scripts/ensure-e2e-ready.sh"

echo ""
echo ">>> make coverage-matrix"
make coverage-matrix

run_step() {
  echo ""
  echo ">>> $1"
  bash "$2"
}

run_step "verify-e2e-spatial-semantic" "$ROOT/scripts/verify-e2e-spatial-semantic.sh"
run_step "verify-e2e-webhook-cloudevents" "$ROOT/scripts/verify-e2e-webhook-cloudevents.sh"
run_step "verify-e2e-families-all" "$ROOT/scripts/verify-e2e-families-all.sh"
run_step "verify-e2e-event-matrix" "$ROOT/scripts/verify-e2e-event-matrix.sh"
run_step "validate-final-premium" "$ROOT/scripts/validate-final-premium.sh"

echo ""
echo ">>> Matrice finale"
make coverage-matrix
python3 -c "
import json
from pathlib import Path
s = json.loads(Path('docs/RULE-COVERAGE-MATRIX.json').read_text())['summary']
print('e2e_covered:', s['e2e_covered'], 'e2e_missing:', s['e2e_missing'])
assert s['e2e_missing'] == 0, 'e2e_missing doit être 0'
"
echo ""
echo "=== BATTERIE VALIDATION OK — stack prête pour test ==="
echo "Frontend: http://localhost:5174/demo"
echo "API:      http://localhost:8081/health"
