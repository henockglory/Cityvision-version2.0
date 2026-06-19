#!/usr/bin/env bash
# Validation finale : coverage-matrix + JSON check
set -euo pipefail
cd ~/citevision-v2
FAIL=0

echo "╔══════════════════════════════════════════════════╗"
echo "║  CitéVision — Validation Finale                  ║"
echo "╚══════════════════════════════════════════════════╝"

echo ""
echo "=== 1. JSON validation fr.json ==="
python3 scripts/validate_json.py frontend/src/i18n/fr.json && echo "[PASS] fr.json valid" || { echo "[FAIL] fr.json invalid"; FAIL=$((FAIL+1)); }

echo ""
echo "=== 2. Coverage matrix ==="
python3 scripts/generate-rule-coverage-matrix.py 2>&1 | tail -15

# Check key metrics
UI_BIENTOT=$(python3 -c "import json; d=json.load(open('docs/RULE-COVERAGE-MATRIX.json')); print(d['summary']['ui_bientot'])")
E2E_MISSING=$(python3 -c "import json; d=json.load(open('docs/RULE-COVERAGE-MATRIX.json')); print(d['summary']['e2e_missing'])")
E2E_LIVE=$(python3 -c "import json; d=json.load(open('docs/RULE-COVERAGE-MATRIX.json')); print(d['summary']['e2e_live'])")
PARTIAL=$(python3 -c "import json; d=json.load(open('docs/RULE-COVERAGE-MATRIX.json')); print(d['summary']['status_partiel'])")

echo ""
echo "=== Métriques clés ==="
echo "  ui_bientot:        $UI_BIENTOT  (cible: 0)"
echo "  e2e_missing:       $E2E_MISSING  (cible: 0)"
echo "  e2e_live:          $E2E_LIVE  (cible: ≥ 20)"
echo "  status_partiel:    $PARTIAL  (17 templates → avec badges)"

if [ "$UI_BIENTOT" -gt 0 ]; then echo "[FAIL] ui_bientot > 0"; FAIL=$((FAIL+1)); fi
if [ "$E2E_MISSING" -gt 0 ]; then echo "[FAIL] e2e_missing > 0"; FAIL=$((FAIL+1)); fi
if [ "$E2E_LIVE" -lt 20 ]; then echo "[WARN] e2e_live < 20 (objectif 15-20 vitrine)"; fi

echo ""
echo "=== 3. Backend Go build ==="
source_path="/usr/local/go/bin"
if [ -d "$source_path" ]; then
    export PATH="$PATH:$source_path"
fi
cd backend && go build ./... 2>&1 && echo "[PASS] Backend build OK" || { echo "[FAIL] Backend build failed"; FAIL=$((FAIL+1)); }
cd ..

echo ""
echo "=== 4. ONNX Runtime CUDA ==="
source ai-engine/.venv/bin/activate
python3 scripts/check_cuda.py 2>&1 | grep -E "CUDA available|providers" || true

echo ""
if [ "$FAIL" -eq 0 ]; then
    echo "╔══════════════════════════════════════════════════╗"
    echo "║  VALIDATION FINALE : PASS ✓                      ║"
    echo "╚══════════════════════════════════════════════════╝"
    exit 0
fi
echo "╔══════════════════════════════════════════════════╗"
echo "║  VALIDATION FINALE : FAIL ($FAIL erreurs)        ║"
echo "╚══════════════════════════════════════════════════╝"
exit 1
