#!/usr/bin/env bash
# Restart AI engine + backend orchestrator to pick up models and camera configs.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
LOGDIR="$ROOT/logs"
AI_PORT="${AI_ENGINE_PORT:-8001}"

echo "==> Restart AI engine"
stop_from_pid "$LOGDIR/ai-engine.pid" 2>/dev/null || true
free_port "$AI_PORT"
sleep 2
# shellcheck source=scripts/lib/cuda-utils.sh
source "$ROOT/scripts/lib/cuda-utils.sh"
setup_cuda_library_path "${ROOT}/ai-engine/.venv/bin/python3"
start_bg ai-engine "$ROOT/ai-engine" \
  "LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-} ${ROOT}/ai-engine/.venv/bin/uvicorn citevision_ai.main:app --host 0.0.0.0 --port $AI_PORT" \
  "$LOGDIR" "$ENV_FILE"

for _ in $(seq 1 90); do
  if curl -sf "http://127.0.0.1:$AI_PORT/health" | grep -q '"yolo_loaded":"true"'; then
    echo "[OK] AI health"
    curl -sf "http://127.0.0.1:$AI_PORT/health" | python3 -m json.tool
    break
  fi
  sleep 2
done

echo "==> Restart backend (orchestrator hot-reload)"
stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
free_port "${API_PORT:-8081}"
sleep 2
GO_BIN="/usr/local/go/bin/go"
[[ -x "$GO_BIN" ]] || GO_BIN="$(command -v go)"
start_bg backend "$ROOT/backend" "$GO_BIN run ./cmd/api" "$LOGDIR" "$ENV_FILE"
for _ in $(seq 1 60); do
  if curl -sf "http://localhost:${API_PORT:-8081}/health" >/dev/null 2>&1; then
    echo "[OK] backend up"
    break
  fi
  sleep 2
done

echo "==> Wait for camera ingest (orchestrator sync ~30s)"
sleep 35
curl -sf "http://127.0.0.1:$AI_PORT/cameras" | python3 -m json.tool | head -30
