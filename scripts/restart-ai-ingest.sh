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
start_bg ai-engine "$ROOT" "bash scripts/run-ai-engine.sh" "$LOGDIR" "$ENV_FILE"

for _ in $(seq 1 90); do
  if curl -sf "http://127.0.0.1:$AI_PORT/health" | grep -q '"yolo_loaded":"true"'; then
    echo "[OK] AI health"
    curl -sf "http://127.0.0.1:$AI_PORT/health" | python3 -m json.tool
    if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
      if ! curl -sf "http://127.0.0.1:$AI_PORT/health" | grep -q '"yolo_cuda":"true"'; then
        echo "[WARN] GPU present but yolo_cuda=false — fixing onnxruntime-gpu…"
        bash "$ROOT/scripts/ensure-ai-stack.sh" --fix --restart-ai --max-attempts=3 \
          --health-url="http://127.0.0.1:$AI_PORT/health" || true
        curl -sf "http://127.0.0.1:$AI_PORT/health" | python3 -m json.tool || true
      fi
    fi
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

bash "$ROOT/scripts/ensure-demo-pipeline.sh"
bash "$ROOT/scripts/ensure-frontend.sh"
