#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/ai-engine"
source "$ROOT/scripts/lib/cuda-utils.sh"
setup_cuda_library_path "$ROOT/ai-engine/.venv/bin/python3"
echo "LD_LIBRARY_PATH=$LD_LIBRARY_PATH"
export YOLO_MODEL_PATH="$ROOT/ai-engine/models/yolov8n.onnx"
"$ROOT/ai-engine/.venv/bin/python3" "$ROOT/scripts/test-yolo-cuda.py"
