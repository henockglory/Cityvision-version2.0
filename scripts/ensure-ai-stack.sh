#!/usr/bin/env bash
# CitéVision v2 — Ensure AI stack (pip extras, models, health gate)
# Usage:
#   bash scripts/ensure-ai-stack.sh [--fix] [--verify-only] [--restart-ai]
#       [--max-attempts N] [--health-url URL]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DO_FIX=false
VERIFY_ONLY=false
RESTART_AI=false
MAX_ATTEMPTS=5
HEALTH_URL=""

for arg in "$@"; do
  case "$arg" in
    --fix) DO_FIX=true ;;
    --verify-only) VERIFY_ONLY=true ;;
    --restart-ai) RESTART_AI=true ;;
    --max-attempts=*) MAX_ATTEMPTS="${arg#*=}" ;;
    --health-url=*) HEALTH_URL="${arg#*=}" ;;
    --help)
      cat <<'EOF'
Usage: bash scripts/ensure-ai-stack.sh [OPTIONS]

Garantit venv IA, extras (InsightFace + PaddleOCR), modèles et gate health.

Options:
  --fix              Appliquer corrections (pip, modèles, restart)
  --verify-only      Vérifier sans corriger (exit 1 si KO)
  --restart-ai       Redémarrer ai-engine après fix
  --max-attempts=N   Tentatives (défaut: 5)
  --health-url=URL   Vérifier yolo/face/plate sur /health (ex: http://127.0.0.1:8001/health)
EOF
      exit 0
      ;;
  esac
done

# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
# shellcheck source=scripts/lib/cuda-utils.sh
source "$ROOT/scripts/lib/cuda-utils.sh"
# shellcheck source=scripts/lib/wsl-root.sh
source "$ROOT/scripts/lib/wsl-root.sh"

ensure_venv_not_on_drvfs
write_build_version 2>/dev/null || true

VENV_SENTINEL="ai-engine/.venv/.installed_ok"
LOGDIR="$ROOT/logs"
VENV_DIR="$(resolve_venv_dir)"
VENV_PY="${VENV_DIR}/bin/python"
VENV_PIP="${VENV_DIR}/bin/pip"
ENV_FILE="$(ensure_env_file "$ROOT" 2>/dev/null || echo "$ROOT/.env")"
load_dotenv "$ENV_FILE"
AI_PORT="${AI_ENGINE_PORT:-8001}"
[[ -z "$HEALTH_URL" ]] && HEALTH_URL="http://127.0.0.1:${AI_PORT}/health"

_log() { echo "$1"; }

_imports_ok() {
  [[ -x "$VENV_PY" ]] || return 1
  "$VENV_PY" -c "import citevision_ai, insightface, paddleocr" 2>/dev/null
}

_yolo_file_ok() {
  local model
  model="$(grep '^CV_YOLO_MODEL=' generated.env 2>/dev/null | cut -d= -f2 | tr -d ' \r' || true)"
  model="${model:-yolov8n.onnx}"
  [[ -f "ai-engine/models/$model" ]] || [[ -f "ai-engine/models/yolov8n.onnx" ]]
}

_models_ok() {
  local n
  n="$(find "$ROOT/ai-engine/models/insightface/models/buffalo_l" -name '*.onnx' 2>/dev/null | wc -l | tr -d ' ')"
  [[ "$n" -ge 3 ]] || return 1
  "$VENV_PY" -c "from paddleocr import PaddleOCR" 2>/dev/null || return 1
  [[ -f "$ROOT/ai-engine/models/secondary/driver_phone.onnx" ]] || return 1
  [[ -f "$ROOT/ai-engine/models/secondary/seatbelt.onnx" ]] || return 1
  return 0
}

_health_keys_ok() {
  local url="$1"
  [[ "$url" == "none" || "$url" == "skip" ]] && return 0
  local gpu_flag=()
  if _gpu_expected; then
    gpu_flag=(--require-gpu)
  fi
  "$VENV_PY" "$ROOT/ai-engine/scripts/check_ai_health.py" --url "$url" "${gpu_flag[@]}"
}

_gpu_expected() {
  command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1
}

_cuda_health_ok() {
  [[ "$HEALTH_URL" == "none" || "$HEALTH_URL" == "skip" ]] && return 0
  if ! _gpu_expected; then
    return 0
  fi
  curl -sf "$HEALTH_URL" 2>/dev/null | grep -q '"yolo_cuda":"true"'
}

verify_stack() {
  _imports_ok || return 1
  _yolo_file_ok || return 1
  _models_ok || return 1
  if [[ "$HEALTH_URL" != "none" && "$HEALTH_URL" != "skip" ]] \
      && curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
    _health_keys_ok "$HEALTH_URL" || return 1
    if _gpu_expected && ! _cuda_health_ok; then
      _log "[WARN] GPU détecté mais yolo_cuda=false (onnxruntime-gpu / cuDNN)"
      return 1
    fi
  fi
  return 0
}

ensure_venv() {
  if [[ ! -d "$VENV_DIR" ]]; then
    _log "[FIX] Création venv Python 3.12…"
    python3.12 -m venv "$VENV_DIR" 2>/dev/null || python3 -m venv "$VENV_DIR"
  fi
}

ensure_pip_extras() {
  ensure_venv
  # shellcheck disable=SC1091
  source "${VENV_DIR}/bin/activate"
  if ! _imports_ok; then
    rm -f "$VENV_SENTINEL"
    _log "[FIX] Installation pip extras (identity + anpr + dev)…"
    local attempt=1
    while (( attempt <= 3 )); do
      pip install --upgrade pip -q 2>/dev/null || true
      if pip install -e 'ai-engine/.[identity,anpr,dev]' 2>&1; then
        ensure_ort_gpu_only "${VENV_DIR}/bin/pip"
        touch "$VENV_SENTINEL"
        return 0
      fi
      _log "[FIX] pip tentative $attempt échouée — retry sans cache…"
      pip install --no-cache-dir -e 'ai-engine/.[identity,anpr,dev]' 2>&1 || true
      ((attempt++)) || true
      sleep 2
    done
    if _imports_ok; then
      ensure_ort_gpu_only "${VENV_DIR}/bin/pip"
      touch "$VENV_SENTINEL"
      return 0
    fi
    return 1
  fi
  touch "$VENV_SENTINEL"
  ensure_ort_gpu_only "${VENV_DIR}/bin/pip"
  return 0
}

ensure_yolo_model() {
  mkdir -p ai-engine/models
  local model
  model="$(grep '^CV_YOLO_MODEL=' generated.env 2>/dev/null | cut -d= -f2 | tr -d ' \r' || true)"
  model="${model:-yolov8n.onnx}"
  if [[ ! -f "ai-engine/models/$model" ]]; then
    _log "[FIX] Téléchargement YOLO $model…"
    YOLO_MODEL="$model" bash "$ROOT/scripts/download-yolo-model.sh" 2>&1 || true
  fi
  if [[ ! -f "ai-engine/models/yolov8n.onnx" ]] && [[ "$model" != "yolov8n.onnx" ]]; then
    _log "[FIX] Fallback yolov8n.onnx…"
    YOLO_MODEL="yolov8n.onnx" bash "$ROOT/scripts/download-yolo-model.sh" 2>&1 || true
  fi
  _yolo_file_ok
}

ensure_download_models() {
  _log "[FIX] Installation complète modèles IA…"
  bash "$ROOT/scripts/install-ai-models.sh" --fix || return 1
}

restart_ai_engine() {
  _log "[FIX] Redémarrage AI engine…"
  stop_from_pid "$LOGDIR/ai-engine.pid"
  free_port "$AI_PORT"
  sleep 2
  mkdir -p "$LOGDIR"
  start_bg ai-engine "$ROOT" "bash scripts/run-ai-engine.sh" "$LOGDIR" "$ENV_FILE"
  local i=0
  while (( i < 120 )); do
    if wait_http_ok "$HEALTH_URL" 5; then
      return 0
    fi
    sleep 2
    ((i += 2))
  done
  return 1
}

apply_fixes() {
  ensure_pip_extras || return 1
  ensure_ort_gpu_only "${VENV_PIP}"
  setup_cuda_library_path "${VENV_DIR}/bin/python3"
  ensure_yolo_model || return 1
  ensure_download_models || return 1
  if [[ "$RESTART_AI" == "true" ]] || curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
    restart_ai_engine || true
  fi
  return 0
}

attempt=1
while (( attempt <= MAX_ATTEMPTS )); do
  if verify_stack; then
    _log "[OK]   AI stack validé (tentative $attempt/$MAX_ATTEMPTS)"
    exit 0
  fi

  if [[ "$VERIFY_ONLY" == "true" ]] && [[ "$DO_FIX" != "true" ]]; then
    _log "[ERR]  AI stack incomplet — verify-only"
    exit 1
  fi

  if [[ "$DO_FIX" != "true" ]]; then
    _log "[ERR]  AI stack incomplet — utilisez --fix"
    exit 1
  fi

  _log "[FIX] Correction AI stack ($attempt/$MAX_ATTEMPTS)…"
  if ! apply_fixes; then
    _log "[ERR]  apply_fixes échoué (tentative $attempt/$MAX_ATTEMPTS)"
  fi
  ((attempt++)) || true
  sleep 3
done

_log "[ERR]  AI stack non validé après $MAX_ATTEMPTS tentatives"
exit 1
