#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test -f "$ROOT/ai-engine/src/citevision_ai/main.py"
test -f "$ROOT/ai-engine/src/citevision_ai/detection/yolo_onnx.py"
test -f "$ROOT/ai-engine/src/citevision_ai/tracking/bytetrack.py"
echo "[PASS] L5 AI detection and tracking modules"
