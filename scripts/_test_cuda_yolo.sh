#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/cuda-utils.sh
source "$ROOT/scripts/lib/cuda-utils.sh"
VENV_PY="$ROOT/ai-engine/.venv/bin/python3"
setup_cuda_library_path "$VENV_PY"
echo "LD_LIBRARY_PATH=$LD_LIBRARY_PATH"
cd "$ROOT/ai-engine"
LD_LIBRARY_PATH="$LD_LIBRARY_PATH" "$VENV_PY" <<'PY'
import onnxruntime as ort
print("available:", ort.get_available_providers())
s = ort.InferenceSession("models/yolov8n.onnx", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
print("active:", s.get_providers())
PY
