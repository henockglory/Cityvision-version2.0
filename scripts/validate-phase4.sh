#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PASS=0; FAIL=0
check() { if "$@"; then echo "[PASS] $1"; PASS=$((PASS+1)); else echo "[FAIL] $1"; FAIL=$((FAIL+1)); fi; }
echo "=== Phase 4: Rules engine ==="
check test -f rules-engine/go.mod
check test -f rules-engine/internal/evaluator/engine.go
check test -f rules-engine/internal/dedup/dedup.go
check test -f rules-engine/cmd/rules-engine/main.go
grep -q 'ET' rules-engine/internal/evaluator/engine.go && check true || check false
echo "Phase 4: PASS=$PASS FAIL=$FAIL"; [ "$FAIL" -eq 0 ]
