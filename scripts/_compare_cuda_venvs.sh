#!/usr/bin/env bash
set -euo pipefail
for ROOT in /home/gheno/citevision-v2 /mnt/c/Users/gheno/citevision; do
  echo "=== $ROOT ==="
  SP="$ROOT/ai-engine/.venv/lib/python3.12/site-packages"
  [[ -d "$SP/nvidia/cudnn/lib" ]] || { echo "no venv"; continue; }
  export LD_LIBRARY_PATH="$SP/nvidia/cudnn/lib:$SP/nvidia/cublas/lib:$SP/nvidia/cuda_runtime/lib"
  "$ROOT/ai-engine/.venv/bin/python3" -c "import onnxruntime as ort; print('ort', ort.__version__)"
  cd "$ROOT/ai-engine"
  "$ROOT/ai-engine/.venv/bin/python3" scripts/_test_ort_cuda.py || true
  echo
done
