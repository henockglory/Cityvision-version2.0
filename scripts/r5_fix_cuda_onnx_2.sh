#!/usr/bin/env bash
# R5 – Fresh install onnxruntime-gpu at the same version to fix conflict
set -e
cd ~/citevision-v2
source ai-engine/.venv/bin/activate

echo "=== Reinstall onnxruntime-gpu cleanly ==="
pip uninstall -y onnxruntime onnxruntime-gpu 2>/dev/null || true

# Install onnxruntime-gpu 1.19.2 - last version with stable WSL CUDA support
# and compatible with numpy/python 3.12
pip install "onnxruntime-gpu==1.19.2" --quiet 2>&1 | tail -5

echo ""
echo "=== Test providers ==="
python3 -c "
import onnxruntime as ort
print('version:', ort.__version__)
providers = ort.get_available_providers()
print('providers:', providers)
print('CUDA enabled:', 'CUDAExecutionProvider' in providers)
"
