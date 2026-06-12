#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test -f "$ROOT/ai-engine/src/citevision_ai/face/insightface_stub.py"
test -f "$ROOT/ai-engine/src/citevision_ai/anpr/paddleocr_stub.py"
echo "[PASS] L10 Face and ANPR stubs"
