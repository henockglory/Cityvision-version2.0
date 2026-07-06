#!/usr/bin/env bash
# Repair ONNX Runtime GPU stack in ai-engine venv (WSL RTX).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lib/cuda-utils.sh
source "$ROOT/scripts/lib/cuda-utils.sh"
VPIP="$ROOT/ai-engine/.venv/bin/pip"
[[ -x "$VPIP" ]] || { echo "[FAIL] venv missing: $ROOT/ai-engine/.venv" >&2; exit 1; }
ensure_ort_gpu_only "$VPIP"
echo "[OK] onnxruntime-gpu ready"
setup_cuda_library_path "$ROOT/ai-engine/.venv/bin/python3"
cd "$ROOT/ai-engine"
"$ROOT/ai-engine/.venv/bin/python3" scripts/_test_ort_cuda.py
