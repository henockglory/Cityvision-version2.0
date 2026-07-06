#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$HOME/citevision-v2}"
V="$ROOT/ai-engine/.venv/bin/python3"
echo "=== GPU ==="
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null || echo "nvidia-smi FAIL"
echo "=== ORT ==="
"$V" -c 'import onnxruntime as ort; print(ort.__version__, ort.get_available_providers())'
# shellcheck source=scripts/lib/cuda-utils.sh
source "$ROOT/scripts/lib/cuda-utils.sh"
setup_cuda_library_path "$V"
echo "=== LD_LIBRARY_PATH ==="
echo "$LD_LIBRARY_PATH" | tr ':' '\n' | head -15
echo "=== YOLO session ==="
cd "$ROOT/ai-engine"
export LD_LIBRARY_PATH
"$V" scripts/_test_ort_cuda.py 2>/dev/null || "$V" - <<'PY'
import onnxruntime as ort
s = ort.InferenceSession("models/yolov8n.onnx", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
print("providers:", s.get_providers())
PY
echo "=== health ==="
curl -sf "http://127.0.0.1:${AI_ENGINE_PORT:-8001}/health" || echo "ai not running"
