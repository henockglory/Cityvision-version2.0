#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"

LOGDIR="$ROOT/logs"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

echo "=== Restart full demo stack (backend → pipeline → frontend) ==="
stop_from_pid "$LOGDIR/backend.pid"
stop_from_pid "$LOGDIR/frontend.pid"
free_port 8081 5174
sleep 2

export PATH="$PATH:/usr/local/go/bin"
GO_BIN="$(command -v go)"
if [[ -z "$GO_BIN" && -x /usr/local/go/bin/go ]]; then
  GO_BIN=/usr/local/go/bin/go
fi
if [[ -z "$GO_BIN" ]]; then
  echo "[FAIL] Go not found — install Go or add to PATH" >&2
  exit 1
fi

echo "[INFO] Building backend binary..."
mkdir -p "$ROOT/backend/bin"
if ! (cd "$ROOT/backend" && "$GO_BIN" build -o "$ROOT/backend/bin/citevision-api" ./cmd/api); then
  echo "[FAIL] Backend build failed" >&2
  exit 1
fi

start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"

BACKEND_PORT="${API_PORT:-8081}"
echo ""
echo "=== Health checks ==="
if ! wait_http_ok "http://localhost:$BACKEND_PORT/health" 90; then
  echo "[FAIL] Backend — tail logs/backend.log"
  tail -20 "$LOGDIR/backend.log"
  exit 1
fi
echo "[OK] Backend http://localhost:$BACKEND_PORT/health"

echo ""
echo "=== AI models + demo pipeline (rules-engine, ingest) ==="
VENV_PY="${ROOT}/ai-engine/.venv/bin/python3"
# shellcheck source=scripts/lib/cuda-utils.sh
source "$ROOT/scripts/lib/cuda-utils.sh"
setup_cuda_library_path "$VENV_PY"

_secondary_models_missing() {
  local sec="$ROOT/ai-engine/models/secondary"
  [[ ! -f "$sec/driver_phone.onnx" || ! -f "$sec/seatbelt.onnx" ]]
}

if _secondary_models_missing; then
  echo "[FIX] Secondary ONNX models missing — full model install…"
  bash "$ROOT/scripts/install-ai-models.sh" --fix || {
    echo "[FAIL] AI models incomplete" >&2
    exit 1
  }
elif ! bash "$ROOT/scripts/install-ai-models.sh" 2>&1; then
  echo "[FIX] Installing missing AI models…"
  bash "$ROOT/scripts/install-ai-models.sh" --fix || {
    echo "[FAIL] AI models incomplete" >&2
    exit 1
  }
fi

AI_PORT="${AI_ENGINE_PORT:-8001}"
stop_from_pid "$LOGDIR/ai-engine.pid" 2>/dev/null || true
pkill -f 'uvicorn citevision_ai.main' 2>/dev/null || true
free_port "$AI_PORT" 2>/dev/null || true
sleep 2

bash "$ROOT/scripts/ensure-demo-pipeline.sh"

if ! "$VENV_PY" "$ROOT/ai-engine/scripts/check_ai_health.py" --url "http://127.0.0.1:${AI_PORT}/health" --require-gpu; then
  curl -sf "http://127.0.0.1:${AI_PORT}/health" || true
  exit 1
fi

echo ""
echo "=== Frontend (last — UI opens on ready stack) ==="
bash "$ROOT/scripts/ensure-frontend.sh"

if [[ "${WATCH_BACKEND:-1}" != "0" ]]; then
  stop_from_pid "$LOGDIR/watch-backend.pid"
  start_bg watch-backend "$ROOT" "bash scripts/watch-backend.sh" "$LOGDIR" "$ENV_FILE"
  echo "[OK] Backend watchdog started"
fi
if [[ "${WATCH_AI_INGEST:-1}" != "0" ]]; then
  stop_from_pid "$LOGDIR/watch-ai-ingest.pid"
  start_bg watch-ai-ingest "$ROOT" "bash scripts/watch-ai-ingest.sh" "$LOGDIR" "$ENV_FILE"
  echo "[OK] AI ingest watchdog started"
fi
if [[ "${WATCH_DEMO_STACK:-1}" != "0" ]]; then
  stop_from_pid "$LOGDIR/watch-demo-stack.pid"
  start_bg watch-demo-stack "$ROOT" "bash scripts/watch-demo-stack.sh" "$LOGDIR" "$ENV_FILE"
  echo "[OK] Demo stack watchdog started"
fi

echo ""
echo "=== Stack ready (6/6 status chips) ==="
echo "  Serveur + Vidéo + IA + GPU + Détections + Alertes"
echo "Done. Demo: http://localhost:5174/demo"
