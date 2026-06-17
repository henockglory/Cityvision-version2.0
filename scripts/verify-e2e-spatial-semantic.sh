#!/usr/bin/env bash
# E2E unitaire : perimeter_breach, unauthorized_exit via EventGenerator (pytest)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/ai-engine"
source .venv/bin/activate
pytest -q tests/test_spatial_semantic_events.py tests/test_sudden_stop.py
echo "=== verify-e2e-spatial-semantic OK ==="
