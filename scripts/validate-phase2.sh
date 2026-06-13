#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PASS=0; FAIL=0
check() { if "$@"; then echo "[PASS] $1"; PASS=$((PASS+1)); else echo "[FAIL] $1"; FAIL=$((FAIL+1)); fi; }
echo "=== Phase 2: Shared schemas & catalog ==="
check test -f shared/schemas/detection.json
check test -f shared/schemas/event.json
check test -f shared/schemas/rule.json
check test -f shared/rule-catalog/intrusion-loitering-line-theft.json
python3 -c "import json; json.load(open('shared/schemas/detection.json'))" && check true || check false
echo "Phase 2: PASS=$PASS FAIL=$FAIL"; [ "$FAIL" -eq 0 ]
