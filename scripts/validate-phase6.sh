#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PASS=0; FAIL=0
check() { if "$@"; then echo "[PASS] $1"; PASS=$((PASS+1)); else echo "[FAIL] $1"; FAIL=$((FAIL+1)); fi; }
echo "=== Phase 6: Scripts & vendor ==="
check test -f scripts/check-wsl.sh
check test -f scripts/setup-wsl.sh
check test -f scripts/start-all.sh
check test -f vendor/README.md
for i in 1 2 3 4 5 6 7 8; do check test -f "scripts/validate-phase${i}.sh"; done
echo "Phase 6: PASS=$PASS FAIL=$FAIL"; [ "$FAIL" -eq 0 ]
