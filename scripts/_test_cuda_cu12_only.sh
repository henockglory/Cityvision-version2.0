#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SP="$ROOT/ai-engine/.venv/lib/python3.12/site-packages"
export LD_LIBRARY_PATH="$SP/nvidia/cudnn/lib:$SP/nvidia/cublas/lib:$SP/nvidia/cuda_runtime/lib"
cd "$ROOT/ai-engine"
source "$ROOT/ai-engine/.venv/bin/activate"
python scripts/_test_ort_cuda.py
