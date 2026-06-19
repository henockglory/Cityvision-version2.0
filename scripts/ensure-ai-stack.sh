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

VENV_SENTINEL="ai-engine/.venv/.installed_ok"
LOGDIR="$ROOT/logs"
ENV_FILE="$(ensure_env_file "$ROOT" 2>/dev/null || echo "$ROOT/.env")"
load_dotenv "$ENV_FILE"
AI_PORT="${AI_ENGINE_PORT:-8001}"
[[ -z "$HEALTH_URL" ]] && HEALTH_URL="http://127.0.0.1:${AI_PORT}/health"

_log() { echo "$1"; }

_imports_ok() {
  [[ -x ai-engine/.venv/bin/python ]] || return 1
  ai-engine/.venv/bin/python -c "import citevision_ai, insightface, paddleocr" 2>/dev/null
}

_yolo_file_ok() {
  local model
  model="$(grep '^CV_YOLO_MODEL=' generated.env 2>/dev/null | cut -d= -f2 | tr -d ' \r' || true)"
  model="${model:-yolov8n.onnx}"
  [[ -f "ai-engine/models/$model" ]] || [[ -f "ai-engine/models/yolov8n.onnx" ]]
}

_models_ok() {
  [[ -d "$ROOT/ai-engine/models/insightface/models/buffalo_l" ]] \
    || [[ -d "$HOME/.insightface/models/buffalo_l" ]] \
    || return 1
  ai-engine/.venv/bin/python -c "from paddleocr import PaddleOCR" 2>/dev/null
}

_health_keys_ok() {
  local url="$1"
  curl -sf "$url" 2>/dev/null | ai-engine/.venv/bin/python -c "
import json, sys
d = json.load(sys.stdin)
keys = ('yolo_loaded', 'face_loaded', 'plate_loaded')
ok = all(str(d.get(k, '')).lower() == 'true' for k in keys)
sys.exit(0 if ok else 1)
" 2>/dev/null
}

verify_stack() {
  _imports_ok || return 1
  _yolo_file_ok || return 1
  _models_ok || return 1
  if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
    _health_keys_ok "$HEALTH_URL" || return 1
  fi
  return 0
}

ensure_venv() {
  if [[ ! -d ai-engine/.venv ]]; then
    _log "[FIX] Création venv Python 3.12…"
    python3.12 -m venv ai-engine/.venv 2>/dev/null || python3 -m venv ai-engine/.venv
  fi
}

ensure_pip_extras() {
  ensure_venv
  # shellcheck disable=SC1091
  source ai-engine/.venv/bin/activate
  if ! _imports_ok; then
    rm -f "$VENV_SENTINEL"
    _log "[FIX] Installation pip extras (identity + anpr + dev)…"
    local attempt=1
    while (( attempt <= 3 )); do
      pip install --upgrade pip -q 2>/dev/null || true
      if pip install -e 'ai-engine/.[identity,anpr,dev]' 2>&1; then
        touch "$VENV_SENTINEL"
        return 0
      fi
      _log "[FIX] pip tentative $attempt échouée — retry sans cache…"
      pip install --no-cache-dir -e 'ai-engine/.[identity,anpr,dev]' 2>&1 || true
      ((attempt++)) || true
      sleep 2
    done
    if _imports_ok; then
      touch "$VENV_SENTINEL"
      return 0
    fi
    return 1
  fi
  touch "$VENV_SENTINEL"
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
  _log "[FIX] Téléchargement / init InsightFace + PaddleOCR…"
  bash "$ROOT/scripts/download-models.sh" --skip-yolo 2>&1
}

restart_ai_engine() {
  _log "[FIX] Redémarrage AI engine…"
  stop_from_pid "$LOGDIR/ai-engine.pid"
  free_port "$AI_PORT"
  sleep 2
  setup_cuda_library_path "$ROOT/ai-engine/.venv/bin/python3"
  mkdir -p "$LOGDIR"
  start_bg ai-engine "$ROOT/ai-engine" \
    "LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-} $ROOT/ai-engine/.venv/bin/uvicorn citevision_ai.main:app --host 0.0.0.0 --port $AI_PORT" \
    "$LOGDIR" "$ENV_FILE"
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
  install_ai_cuda_deps "$ROOT/ai-engine/.venv/bin/pip"
  setup_cuda_library_path "$ROOT/ai-engine/.venv/bin/python3"
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
  apply_fixes || _log "[WARN] apply_fixes partiellement échoué"
  ((attempt++)) || true
  sleep 3
done

_log "[ERR]  AI stack non validé après $MAX_ATTEMPTS tentatives"
exit 1
