#!/usr/bin/env bash
# Phase D — E2E pour toutes les règles UI « Disponibles » (matrice + scripts live uniques + pytest catalogue)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FAIL=0
pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1"; FAIL=$((FAIL + 1)); }

echo "╔══════════════════════════════════════════════════╗"
echo "║  Phase D — E2E règles Disponibles (matrice)     ║"
echo "╚══════════════════════════════════════════════════╝"

echo ""
echo ">>> Génération matrice de couverture"
if ! python3 "$ROOT/scripts/generate-rule-coverage-matrix.py"; then
  echo "[FAIL] generate-rule-coverage-matrix.py"
  exit 1
fi

MATRIX="$ROOT/docs/RULE-COVERAGE-MATRIX.json"
if [ ! -f "$MATRIX" ]; then
  echo "[FAIL] matrice absente: $MATRIX"
  exit 1
fi

DISPONIBLES=$(python3 -c "
import json
from pathlib import Path
data = json.loads(Path('$MATRIX').read_text())
print(sum(1 for r in data['rows'] if r.get('ui_tab')=='Disponibles'))
")
echo "[INFO] Templates UI Disponibles: $DISPONIBLES"

LIVE_SCRIPTS=$(python3 <<'PY'
import json
from pathlib import Path
data = json.loads(Path("docs/RULE-COVERAGE-MATRIX.json").read_text())
seen = set()
for row in data["rows"]:
    if row.get("ui_tab") != "Disponibles":
        continue
    if row.get("e2e_mode") != "live":
        continue
    script = row.get("e2e_script")
    if script:
        seen.add(script)
for s in sorted(seen):
    print(s)
PY
)

echo ""
echo ">>> Scripts E2E live uniques (Disponibles)"
if [ -z "$LIVE_SCRIPTS" ]; then
  echo "[WARN] aucun script live — fallback pytest catalogue uniquement"
else
  while IFS= read -r script; do
    [ -z "$script" ] && continue
    path="$ROOT/scripts/$script"
    if [ ! -f "$path" ]; then
      fail "script manquant: $script"
      continue
    fi
    echo ""
    echo ">>> $script"
    if bash "$path"; then
      pass "$script"
    else
      fail "$script"
    fi
  done <<< "$LIVE_SCRIPTS"
fi

echo ""
echo ">>> Pytest catalogue (couverture unitaire Disponibles)"
if bash "$ROOT/scripts/verify-e2e-pytest-catalog.sh"; then
  pass "verify-e2e-pytest-catalog.sh"
else
  fail "verify-e2e-pytest-catalog.sh"
fi

echo ""
echo ">>> Synthèse matrice E2E"
python3 -c "
import json
from pathlib import Path
d = json.loads(Path('docs/RULE-COVERAGE-MATRIX.json').read_text())['summary']
print(f\"  Disponibles UI: {d['ui_disponibles']}\")
print(f\"  E2E live: {d['e2e_live']} | pytest-fallback: {d['e2e_pytest_fallback']} | non testé: {d['e2e_not_tested']}\")
"

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "=== verify-e2e-disponibles OK ==="
  exit 0
fi
echo "=== verify-e2e-disponibles FAILED ($FAIL) ==="
exit 1
