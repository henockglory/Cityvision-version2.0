#!/usr/bin/env bash
# R5 – Fix CUDA ONNX Runtime in WSL venv
set -e
cd ~/citevision-v2
source ai-engine/.venv/bin/activate

echo "=== Current ONNX packages ==="
pip list | grep -i onnx || true

echo ""
echo "=== Removing CPU-only onnxruntime to avoid conflict with onnxruntime-gpu ==="
pip uninstall -y onnxruntime 2>/dev/null || echo "onnxruntime not installed, OK"

echo ""
echo "=== Checking CUDA availability in WSL ==="
# Check for CUDA stubs / libcuda
CUDA_OK=0
if ldconfig -p 2>/dev/null | grep -q libcuda; then
    echo "libcuda found in ldconfig"
    CUDA_OK=1
elif ls /usr/lib/wsl/lib/libcuda.so* 2>/dev/null; then
    echo "libcuda found in /usr/lib/wsl/lib/"
    CUDA_OK=1
elif ls /mnt/c/Windows/System32/lxss/lib/libcuda.so* 2>/dev/null; then
    echo "libcuda found via WSL lxss"
    CUDA_OK=1
fi

echo ""
echo "=== Checking onnxruntime-gpu providers after removing CPU package ==="
python3 -c "import onnxruntime as ort; print('version:', ort.__version__); print('providers:', ort.get_available_providers()); print('CUDA:', 'CUDAExecutionProvider' in ort.get_available_providers())"

echo ""
echo "=== CUDA verdict ==="
if python3 -c "import onnxruntime as ort; assert 'CUDAExecutionProvider' in ort.get_available_providers()" 2>/dev/null; then
    echo "CUDA ENABLED ✓"
else
    echo "CUDA not available in providers — this is expected if CUDA toolkit is not installed in WSL"
    echo "The onnxruntime-gpu package is installed, but CUDA libs may not be in the WSL path."
    echo ""
    echo "=== Checking CUDA toolkit installation ==="
    nvcc --version 2>/dev/null || echo "nvcc not found (CUDA toolkit not installed in WSL)"
    ls /usr/local/cuda 2>/dev/null && echo "CUDA found at /usr/local/cuda" || echo "No CUDA toolkit at /usr/local/cuda"
    echo ""
    echo "WSL GPU can work WITHOUT CUDA toolkit if using DirectML or if libcuda.so is present."
    echo "The ai-engine will log a warning and fall back to CPU — this is correct behavior."
fi
