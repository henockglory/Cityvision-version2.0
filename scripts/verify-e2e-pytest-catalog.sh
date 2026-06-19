#!/usr/bin/env bash
# E2E catalogue : pytest couvrant les event_type Disponibles (preuve unitaire + intégration IA)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/ai-engine"
export E2E_MODE=1
PY="$ROOT/ai-engine/.venv/bin/python3"
if [ ! -x "$PY" ]; then
  echo "[FAIL] venv manquante — lancez: pip install -e '.[identity,anpr,dev]' dans ai-engine"
  exit 1
fi
echo "=== verify-e2e-pytest-catalog ==="
"$PY" -m pytest -q \
  tests/test_event_generator.py \
  tests/test_spatial_semantic_events.py \
  tests/test_sudden_stop.py \
  tests/test_scene_state_e2e.py \
  tests/test_behavior.py \
  tests/test_category_c_detectors.py \
  tests/test_correlation.py \
  tests/test_resource_budget.py \
  --tb=line
echo "=== verify-e2e-pytest-catalog OK ==="
