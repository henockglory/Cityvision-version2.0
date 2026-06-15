#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../ai-engine"
source .venv/bin/activate
pip install -q nvidia-cudnn-cu12 2>/dev/null || true
CUDNN_LIB=$(python3 -c "import nvidia.cudnn; import os; print(os.path.join(os.path.dirname(nvidia.cudnn.__file__), 'lib'))" 2>/dev/null || echo "")
export LD_LIBRARY_PATH="${CUDNN_LIB}:${LD_LIBRARY_PATH:-}"
export PYTHONPATH=src
python3 ../scripts/test-yolo-cuda.py
