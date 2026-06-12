#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test -f "$ROOT/video-engine/CMakeLists.txt"
test -f "$ROOT/video-engine/README.md"
echo "[PASS] L12 Video engine CMake project"
