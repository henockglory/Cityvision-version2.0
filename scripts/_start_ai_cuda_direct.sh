#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
SP="$ROOT/ai-engine/.venv/lib/python3.12/site-packages"
export LD_LIBRARY_PATH="$SP/nvidia/cudnn/lib:$SP/nvidia/cublas/lib:$SP/nvidia/cuda_runtime/lib"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
stop_from_pid "$ROOT/logs/ai-engine.pid" 2>/dev/null || true
pkill -f 'uvicorn citevision_ai.main' 2>/dev/null || true
free_port 8001 2>/dev/null || true
sleep 2
cd "$ROOT/ai-engine"
export YOLO_DEVICE=cuda
exec "$ROOT/ai-engine/.venv/bin/uvicorn" citevision_ai.main:app --host 0.0.0.0 --port 8001
