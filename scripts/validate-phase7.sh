#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PASS=0; FAIL=0
check() { if "$@"; then echo "[PASS] $1"; PASS=$((PASS+1)); else echo "[FAIL] $1"; FAIL=$((FAIL+1)); fi; }
echo "=== Phase 7: Documentation ==="
for doc in CLARIFICATIONS PROGRESS OPEN_QUESTIONS RESUME ARCHITECTURE PORTS; do
  check test -f "docs/${doc}.md"
done
echo "Phase 7: PASS=$PASS FAIL=$FAIL"; [ "$FAIL" -eq 0 ]
