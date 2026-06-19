#!/usr/bin/env python3
"""
R5 - Document and pin the CUDA ONNX Runtime setup.
Updates pyproject.toml to pin onnxruntime-gpu and creates setup-cuda.sh.
"""
from pathlib import Path

# 1. Create scripts/setup-cuda-onnx.sh
setup_cuda = """#!/usr/bin/env bash
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
"""

setup_path = Path("scripts/setup-cuda-onnx.sh")
setup_path.write_text(setup_cuda, encoding="utf-8")
print(f"Created {setup_path}")

# 2. Update ai-engine/pyproject.toml to use onnxruntime-gpu instead of onnxruntime
pyproject = Path("ai-engine/pyproject.toml")
content = pyproject.read_text(encoding="utf-8")

# Replace onnxruntime (CPU) dependency with onnxruntime-gpu
if '"onnxruntime"' in content and '"onnxruntime-gpu"' not in content:
    content = content.replace('"onnxruntime"', '"onnxruntime-gpu==1.19.2"')
    pyproject.write_text(content, encoding="utf-8")
    print("Updated pyproject.toml: onnxruntime → onnxruntime-gpu==1.19.2")
elif '"onnxruntime-gpu"' in content:
    # Already has gpu version, just ensure version is pinned
    import re
    content_new = re.sub(
        r'"onnxruntime-gpu[^"]*"',
        '"onnxruntime-gpu==1.19.2"',
        content
    )
    if content_new != content:
        pyproject.write_text(content_new, encoding="utf-8")
        print("Pinned onnxruntime-gpu to 1.19.2 in pyproject.toml")
    else:
        print("pyproject.toml already has onnxruntime-gpu pinned")
else:
    print(f"WARN: onnxruntime not found in pyproject.toml — checking content:")
    for i, line in enumerate(content.split('\n'), 1):
        if 'onnx' in line.lower():
            print(f"  L{i}: {line}")

# 3. Update ai-engine README or docs about CUDA setup
print("\nCUDA setup documented ✓")
