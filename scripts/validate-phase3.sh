#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PASS=0; FAIL=0
check() { if "$@"; then echo "[PASS] $1"; PASS=$((PASS+1)); else echo "[FAIL] $1"; FAIL=$((FAIL+1)); fi; }
echo "=== Phase 3: AI engine ==="
check test -f ai-engine/pyproject.toml
check test -f ai-engine/src/citevision_ai/main.py
check test -f ai-engine/src/citevision_ai/detection/yolo_onnx.py
check test -f ai-engine/src/citevision_ai/tracking/bytetrack.py
check test -f ai-engine/src/citevision_ai/budget/resource_budget.py
grep -q '8001' .env.example && check true || check false
echo "Phase 3: PASS=$PASS FAIL=$FAIL"; [ "$FAIL" -eq 0 ]
