#!/usr/bin/env bash
# Install + verify all AI models (YOLO, InsightFace, PaddleOCR, secondary ONNX).
# Extensible via shared/ai-stack-registry.json + shared/ai-models.json.
#
# Usage:
#   bash scripts/install-ai-models.sh           # verify only
#   bash scripts/install-ai-models.sh --fix     # download/build missing + verify
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
DO_FIX=false
ALLOW_CPU=false
for arg in "$@"; do
  case "$arg" in
    --fix) DO_FIX=true ;;
    --allow-cpu) ALLOW_CPU=true ;;
    --help)
      echo "Usage: bash scripts/install-ai-models.sh [--fix] [--allow-cpu]"
      exit 0
      ;;
  esac
done

# shellcheck source=scripts/lib/cuda-utils.sh
source "$ROOT/scripts/lib/cuda-utils.sh"
VENV_PY="${ROOT}/ai-engine/.venv/bin/python3"
VENV_PIP="${ROOT}/ai-engine/.venv/bin/pip"

if [[ ! -x "$VENV_PY" ]]; then
  echo "[ERR] venv missing — run: bash scripts/ensure-ai-stack.sh --fix" >&2
  exit 1
fi

ensure_secondary_models() {
  echo "=== Secondary ONNX models (phone + seatbelt) ==="
  if bash "$ROOT/scripts/download-secondary-models.sh"; then
    echo "[OK] Secondary models present"
    return 0
  fi
  echo "[FIX] Building secondary ONNX models…"
  bash "$ROOT/scripts/build-secondary-models.sh"
}

if [[ "$DO_FIX" == "true" ]]; then
  echo "=== [FIX] pip extras + ONNX Runtime GPU ==="
  # shellcheck disable=SC1091
  source "${ROOT}/ai-engine/.venv/bin/activate"
  pip install -e 'ai-engine/.[identity,anpr,dev]' 2>&1 || pip install --no-cache-dir -e 'ai-engine/.[identity,anpr,dev]'
  # Paddle 3.3.x + oneDNN PIR crash on CPU — pin stable CPU build.
  "$VENV_PIP" install --no-cache-dir 'paddlepaddle==3.2.2' 2>&1 || \
    "$VENV_PIP" install --no-cache-dir 'paddlepaddle>=3.2.1,<3.3.0' 2>&1 || true
  ensure_ort_gpu_only "$VENV_PIP"
  "$VENV_PIP" uninstall -y onnxruntime 2>/dev/null || true
  install_ai_cuda_deps "$VENV_PIP"
  setup_cuda_library_path "$VENV_PY"
  bash "$ROOT/scripts/_copy_working_cudnn.sh" 2>/dev/null || true

  echo "=== [FIX] Primary models (YOLO, InsightFace, PaddleOCR) ==="
  bash "$ROOT/scripts/download-models.sh"

  ensure_secondary_models || {
    echo "[ERR] secondary models build/verify failed" >&2
    exit 1
  }
fi

echo "=== Verify AI stack (inference smoke tests) ==="
ensure_ort_gpu_only "$VENV_PIP"
setup_cuda_library_path "$VENV_PY"
export FLAGS_use_mkldnn=0
export FLAGS_use_onednn=0
export FLAGS_enable_pir_api=0
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
bash "$ROOT/scripts/_copy_working_cudnn.sh" 2>/dev/null || true
VERIFY_ARGS=(--device "${YOLO_DEVICE:-cuda}")
[[ "$ALLOW_CPU" == "true" ]] && VERIFY_ARGS+=(--allow-cpu)
if ! "$VENV_PY" "$ROOT/ai-engine/scripts/verify_ai_stack.py" "${VERIFY_ARGS[@]}"; then
  echo "[ERR] Verification failed — use: bash scripts/install-ai-models.sh --fix" >&2
  exit 1
fi
echo "[OK] All AI models installed and verified"

# [J.91] Org custom models sync stub — future hook to push data/orgs/*/ai-models into AI engine reload.
sync_org_models_stub() {
  local org_root="${ORG_MODELS_ROOT:-${DATA_ROOT:-data}/orgs}"
  if [[ ! -d "$org_root" ]]; then
    echo "[SKIP] Org models sync stub — no dir: $org_root"
    return 0
  fi
  echo "=== Org custom models sync (stub) ==="
  while IFS= read -r reg; do
    echo "  [stub] would sync registry: $reg"
  done < <(find "$org_root" -name 'org-models.json' -print 2>/dev/null || true)
}
sync_org_models_stub
