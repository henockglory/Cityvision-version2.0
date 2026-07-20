#!/usr/bin/env bash
# Remove CPU-only onnxruntime (pulled by insightface) — conflicts with onnxruntime-gpu.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VENV="${ROOT}/ai-engine/.venv"
# shellcheck disable=SC1091
source "${VENV}/bin/activate"
# shellcheck source=scripts/lib/cuda-utils.sh
source "${ROOT}/scripts/lib/cuda-utils.sh"

echo "=== Before ==="
pip show onnxruntime onnxruntime-gpu 2>/dev/null | grep -E '^Name:|^Version:' || true

echo "=== Removing CPU-only onnxruntime ==="
pip uninstall -y onnxruntime 2>/dev/null || true

echo "=== Ensuring onnxruntime-gpu 1.19.2 ==="
pip install -q "onnxruntime-gpu==1.19.2"

install_ai_cuda_deps "${VENV}/bin/pip"
setup_cuda_library_path "${VENV}/bin/python"

echo "=== After ==="
python - <<'PY'
import onnxruntime as ort
print("version:", ort.__version__)
print("providers:", ort.get_available_providers())
PY

echo "=== CUDA session test ==="
python ai-engine/scripts/_test_ort_cuda.py
