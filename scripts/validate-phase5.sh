#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PASS=0; FAIL=0
check() { if "$@"; then echo "[PASS] $1"; PASS=$((PASS+1)); else echo "[FAIL] $1"; FAIL=$((FAIL+1)); fi; }
echo "=== Phase 5: Video engine ==="
check test -f video-engine/CMakeLists.txt
check test -f video-engine/src/main.cpp
check test -f video-engine/src/dual_pipeline.cpp
check test -f video-engine/include/citevision/config.hpp
grep -q '9011' video-engine/include/citevision/config.hpp && check true || check false
echo "Phase 5: PASS=$PASS FAIL=$FAIL"; [ "$FAIL" -eq 0 ]
