#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "========================================"
echo "  Citévision 2.0 — Final Validation"
echo "========================================"

FAIL=0
for i in $(seq 1 13); do
  script="scripts/validate-l${i}.sh"
  if ! bash "$script"; then
    FAIL=$((FAIL + 1))
  fi
done

echo ""
echo "==> Running pytest"
if bash scripts/run-all-tests.sh; then
  echo "[PASS] pytest"
else
  echo "[FAIL] pytest"
  FAIL=$((FAIL + 1))
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "ALL VALIDATIONS PASSED"
  exit 0
else
  echo "$FAIL VALIDATION(S) FAILED"
  exit 1
fi
