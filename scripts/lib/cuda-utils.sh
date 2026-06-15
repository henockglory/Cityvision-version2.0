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
  for rel in nvidia/cudnn/lib nvidia/cublas/lib nvidia/cuda_runtime/lib; do
    p="$site_pkg/$rel"
    if [[ -d "$p" ]]; then
      paths="${paths:+$paths:}$p"
    fi
  done
  if [[ -n "$paths" ]]; then
    export LD_LIBRARY_PATH="${paths}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  fi
}

install_ai_cuda_deps() {
  local venv_pip="${1:?pip path}"
  "$venv_pip" install -q onnxruntime-gpu 2>/dev/null || true
  "$venv_pip" install -q nvidia-cudnn-cu12 nvidia-cublas-cu12 nvidia-cuda-runtime-cu12 2>/dev/null || true
}
