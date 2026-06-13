#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PASS=0; FAIL=0
check() { if "$@"; then echo "[PASS] $1"; PASS=$((PASS+1)); else echo "[FAIL] $1"; FAIL=$((FAIL+1)); fi; }
echo "=== Phase 8: Tests ==="
cd ai-engine
if [ -d .venv ]; then source .venv/bin/activate; fi
pip install -q -e . pytest pytest-asyncio httpx 2>/dev/null || pip install -q -r requirements.txt
pytest -q && check pytest || check false
cd "$ROOT"
cd rules-engine
go test ./... && check go-test || check false
cd "$ROOT"
check test -f tests/e2e/README.md
check test -f .github/workflows/ci.yml
echo "Phase 8: PASS=$PASS FAIL=$FAIL"; [ "$FAIL" -eq 0 ]
