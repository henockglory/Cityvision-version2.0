#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test -f "$ROOT/ai-engine/src/citevision_ai/budget/resource_budget.py"
echo "[PASS] L6 ResourceBudgetManager present"
