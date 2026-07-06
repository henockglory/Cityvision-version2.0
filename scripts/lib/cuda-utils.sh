#!/usr/bin/env bash
# Configure LD_LIBRARY_PATH for ONNX Runtime CUDA (cuDNN via pip).
setup_cuda_library_path() {
  local venv_python="${1:-python3}"
  if ! command -v "$venv_python" >/dev/null 2>&1; then
    return 0
  fi
  local venv_root site_pkg paths="" rel p
  venv_root="$(cd "$(dirname "$venv_python")/.." && pwd)"
  site_pkg=$(find "$venv_root/lib" -maxdepth 2 -type d -name site-packages 2>/dev/null | head -1)
  [[ -n "$site_pkg" ]] || return 0
  # ORT 1.19.x needs CUDA 12 + cuDNN 9 — do NOT add cu13/torch paths (breaks cudnnCreate).
  for rel in \
    nvidia/cudnn/lib \
    nvidia/cublas/lib \
    nvidia/cuda_runtime/lib \
    nvidia/cufft/lib \
    nvidia/curand/lib; do
    p="$site_pkg/$rel"
    if [[ -d "$p" ]] && [[ ":$paths:" != *":$p:"* ]]; then
      paths="${paths:+$paths:}$p"
    fi
  done
  if [[ -n "$paths" ]]; then
    export LD_LIBRARY_PATH="${paths}"
  fi
}

install_ai_cuda_deps() {
  local venv_pip="${1:?pip path}"
  local venv_root="${venv_pip%/bin/pip}"
  local site_pkg="$venv_root/lib/python3.12/site-packages"
  "$venv_pip" install -q "onnxruntime-gpu==1.19.2" 2>/dev/null || true
  # ORT 1.19.x + WSL: cuDNN 9.23 (torch) breaks cudnnCreate — pin 9.1.x when online.
  if ! "$venv_pip" install -q \
    "nvidia-cudnn-cu12==9.1.0.70" \
    "nvidia-cublas-cu12" \
    "nvidia-cuda-runtime-cu12" \
    "nvidia-curand-cu12" \
    "nvidia-cufft-cu12" 2>/dev/null; then
    local fallback src dst
    for fallback in \
      "${HOME}/.citevision-v2/ai-engine-venv/lib/python3.12/site-packages/nvidia/cudnn/lib" \
      "/mnt/c/Users/gheno/citevision/ai-engine/.venv/lib/python3.12/site-packages/nvidia/cudnn/lib"; do
      if [[ -f "$fallback/libcudnn.so.9" ]]; then
        src="$fallback"
        dst="$site_pkg/nvidia/cudnn/lib"
        mkdir -p "$dst"
        cp -a "$src"/. "$dst"/
        break
      fi
    done
  fi
}

# insightface pulls CPU-only `onnxruntime`, which breaks CUDA (mixed 1.27 + 1.19 .so).
ensure_ort_gpu_only() {
  local venv_pip="${1:?pip path}"
  local venv_python="${venv_pip%/bin/pip}/bin/python3"
  "$venv_pip" uninstall -y onnxruntime >/dev/null 2>&1 || true
  "$venv_pip" install -q --force-reinstall --no-deps "onnxruntime-gpu==1.19.2" 2>/dev/null || \
    "$venv_pip" install -q "onnxruntime-gpu==1.19.2" || true
  "$venv_pip" uninstall -y onnxruntime >/dev/null 2>&1 || true
  if ! "$venv_python" -c "import onnxruntime as ort; assert hasattr(ort, 'get_available_providers'); assert ort.__version__.startswith('1.19')" 2>/dev/null; then
    "$venv_pip" install -q --force-reinstall "onnxruntime-gpu==1.19.2" || true
    "$venv_pip" uninstall -y onnxruntime >/dev/null 2>&1 || true
  fi
  install_ai_cuda_deps "$venv_pip"
}
