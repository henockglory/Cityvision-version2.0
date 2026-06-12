#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test -d "$ROOT/ai-engine/tests"
test -f "$ROOT/ai-engine/tests/test_resource_budget.py"
echo "[PASS] L11 pytest tests present"
