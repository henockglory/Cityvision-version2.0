#!/usr/bin/env bash
# Configure ONNX Runtime GPU pour WSL (RTX 4050 confirmé)
# Prerequis : python3 virtualenv déjà crée (make venv ou pip install -e '.[dev]')
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source ai-engine/.venv/bin/activate

echo "=== Configuration ONNX Runtime GPU pour WSL ==="
echo "Suppression de onnxruntime CPU-only si présent..."
pip uninstall -y onnxruntime 2>/dev/null || true

echo "Installation de onnxruntime-gpu==1.19.2 (compatible Python 3.12 + CUDA WSL)..."
pip install "onnxruntime-gpu==1.19.2" --quiet

echo "Vérification..."
python3 -c "
import onnxruntime as ort
print('Version:', ort.__version__)
providers = ort.get_available_providers()
print('Providers:', providers)
if 'CUDAExecutionProvider' in providers:
    print('[OK] CUDA activé — la RTX 4050 sera utilisée pour YOLO')
else:
    print('[WARN] CUDA non disponible — CPU fallback (vérifier nvidia-smi)')
"
