#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="$PATH:/usr/local/go/bin"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
# shellcheck source=scripts/lib/cuda-utils.sh
source "$ROOT/scripts/lib/cuda-utils.sh"

LOGDIR="$ROOT/logs"
mkdir -p "$LOGDIR"
export CITEVISION_LOGDIR="$LOGDIR"

echo "=== Citevision v2 Start (Linux/WSL) ==="
echo ""

ENV_FILE="$(ensure_env_file "$ROOT")"
sync_project_root "$ROOT"
load_dotenv "$ENV_FILE"

ensure_docker_ready 120 install || exit 1

if command -v nvidia-smi >/dev/null 2>&1; then
  echo "[OK] NVIDIA GPU detected:"
  nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || true
else
  echo "[WARN] nvidia-smi not available — AI will fall back to CPU (see docs/GPU-WSL2.md)"
fi

echo "[INFO] Starting infrastructure..."
bash "$ROOT/scripts/ensure-video-storage.sh"
docker compose -f infra/docker-compose.yml --env-file "$ENV_FILE" up -d
# minio-init is a one-shot job — do not use `compose --wait` on the full stack
sleep 5
if ! wait_http_ok "http://localhost:${MQTT_PORT:-1884}" 5 2>/dev/null; then
  : # Mosquitto has no HTTP health — brief pause for broker readiness
fi
echo "[OK] Infrastructure healthy"
if docker ps --format '{{.Names}}' | grep -q citevision-v2-minio; then
  MINIO_API="${MINIO_API_PORT:-9003}"
  MINIO_CONSOLE="${MINIO_CONSOLE_PORT:-9004}"
  if wait_http_ok "http://localhost:$MINIO_API/minio/health/live" 30 2>/dev/null; then
    echo "[OK] MinIO API http://localhost:$MINIO_API (console :$MINIO_CONSOLE)"
    echo "     Buckets: citevision-evidence (preuves), ${MINIO_BUCKET:-citevision-recordings} (enregistrements)"
    echo "     Env: MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_BUCKET, PUBLIC_API_BASE"
  else
    echo "[WARN] MinIO not ready — evidence upload will fall back to metadata-only"
  fi
fi
if docker ps --format '{{.Names}}' | grep -q citevision-v2-go2rtc; then
  docker restart citevision-v2-go2rtc >/dev/null 2>&1 || true
  sleep 3
fi

# ── AI stack (venv, extras, modèles) — auto-fix, jamais de fallback pip minimal ──
echo "[INFO] Vérification / correction AI stack…"
if ! bash "$ROOT/scripts/ensure-ai-stack.sh" --fix --max-attempts=5; then
  echo "[FAIL] AI stack incomplet après remédiation automatique" >&2
  exit 1
fi
echo "[OK] AI stack prêt"

if ! ensure_frontend_deps "$ROOT"; then
  echo "[FAIL] Frontend dependencies missing or wrong platform — run: bash scripts/setup-wsl.sh" >&2
  exit 1
fi

BACKEND_PORT="${API_PORT:-8081}"
AI_PORT="${AI_ENGINE_PORT:-8001}"
RULES_PORT="${RULES_ENGINE_PORT:-8010}"
GO_BIN="/usr/local/go/bin/go"
if [[ ! -x "$GO_BIN" ]]; then
  GO_BIN="$(command -v go || true)"
fi

free_port 8081 8001 8010
free_port 5174 5175 5176 5177
sleep 1

bash "$ROOT/scripts/ensure-rules-sync-env.sh" --static-only
load_dotenv "$ENV_FILE"

start_bg backend "$ROOT/backend" "$GO_BIN run ./cmd/api" "$LOGDIR" "$ENV_FILE"
sleep 3

echo ""
echo "[INFO] Waiting for backend (first run may download Go modules)..."
if ! wait_service_with_retry backend "http://localhost:$BACKEND_PORT/health" \
    "$LOGDIR/backend.pid" "$GO_BIN run ./cmd/api" "$ROOT/backend" "$LOGDIR" "$ENV_FILE" 120 2; then
  exit 1
fi

echo "[INFO] Flux vidéo démo — sync fichiers MP4 + enregistrement go2rtc…"
bash "$ROOT/scripts/ensure-demo-streams.sh" || echo "[WARN] ensure-demo-streams — poursuite"

bash "$ROOT/scripts/ensure-rules-sync-env.sh" --resolve-org
load_dotenv "$ENV_FILE"

start_bg rules-engine "$ROOT/rules-engine" "$GO_BIN run ./cmd/rules-engine" "$LOGDIR" "$ENV_FILE"
VENV_PY="${ROOT}/ai-engine/.venv/bin/python3"
setup_cuda_library_path "$VENV_PY"
bash "$ROOT/scripts/_copy_working_cudnn.sh" 2>/dev/null || true
ensure_ort_gpu_only "${ROOT}/ai-engine/.venv/bin/pip" 2>/dev/null || true
start_bg ai-engine "$ROOT" "bash scripts/run-ai-engine.sh" "$LOGDIR" "$ENV_FILE"

echo ""
echo "[INFO] Waiting for AI Engine (first run compiles ONNX session)..."
AI_GATE_OK=false
if wait_http_ok "http://localhost:$AI_PORT/health" 120; then
  echo "[OK] AI Engine reachable — http://localhost:$AI_PORT"
  if bash "$ROOT/scripts/ensure-ai-stack.sh" --fix --restart-ai \
      --health-url="http://127.0.0.1:$AI_PORT/health" --max-attempts=5; then
    AI_GATE_OK=true
    echo "[OK] Gate IA validée (registre ai-stack-registry.json + CUDA si GPU)"
  fi
fi
if [[ "$AI_GATE_OK" != "true" ]]; then
  echo "[FAIL] Gate IA non validée après remédiation automatique" >&2
  if [[ -x "$VENV_PY" ]]; then
    gpu_flag=()
    if command -v nvidia-smi >/dev/null 2>&1; then
      gpu_flag=(--require-gpu)
    fi
    "$VENV_PY" "$ROOT/ai-engine/scripts/check_ai_health.py" \
      --url "http://127.0.0.1:$AI_PORT/health" "${gpu_flag[@]}" 2>&1 || true
  fi
  echo "       Consultez logs/ai-engine.log — fix: bash scripts/install-ai-models.sh --fix" >&2
  exit 1
fi

echo ""
echo "[INFO] Waiting for Rules Engine..."
if ! wait_service_with_retry rules-engine "http://localhost:$RULES_PORT/health" \
    "$LOGDIR/rules-engine.pid" "$GO_BIN run ./cmd/rules-engine" "$ROOT/rules-engine" "$LOGDIR" "$ENV_FILE" 30 2; then
  exit 1
fi

echo "[INFO] Sync spatial config → AI ingest (demo pipeline)"
curl -sf -X POST "http://127.0.0.1:${BACKEND_PORT}/api/v1/internal/ingest/resync-spatial" \
  -H "X-Internal-Key: ${INTERNAL_API_KEY:-changeme_internal_service_key}" >/dev/null || true
sleep 15

bash "$ROOT/scripts/verify-ai-ingest.sh" || {
  echo "[WARN] ingest slow on first pass — one AI restart"
  bash "$ROOT/scripts/restart-ai-engine.sh"
  sleep 15
  bash "$ROOT/scripts/verify-ai-ingest.sh"
}

free_port 5174 5175 5176 5177
sleep 1
start_bg frontend "$ROOT/frontend" "npm run dev -- --host 0.0.0.0 --port 5174 --strictPort" "$LOGDIR" "$ENV_FILE"

echo ""
echo "[INFO] Waiting for frontend (Vite dev server)..."
if ! wait_service_with_retry frontend "http://localhost:5174/" \
    "$LOGDIR/frontend.pid" "npm run dev -- --host 0.0.0.0 --port 5174 --strictPort" "$ROOT/frontend" "$LOGDIR" "$ENV_FILE" 90 2; then
  echo "[FAIL] Frontend not reachable on port 5174 — see logs/frontend.log" >&2
  exit 1
fi

echo ""
echo "=== Citevision v2 Running ==="
echo "  Frontend:     http://localhost:5174"
echo "  Setup:        http://localhost:5174/setup"
echo "  Backend:      http://localhost:$BACKEND_PORT/health"
echo "  AI Engine:    http://localhost:$AI_PORT/health"
echo "  Rules Engine: http://localhost:$RULES_PORT/health"
echo "  go2rtc:       http://localhost:1984"
echo "  MinIO API:    http://localhost:${MINIO_API_PORT:-9003}"
echo "  MinIO UI:     http://localhost:${MINIO_CONSOLE_PORT:-9004}"
echo ""
echo "Stop: bash scripts/stop-linux.sh"
echo "Doctor: bash scripts/doctor-linux.sh"

if [[ "${WATCH_BACKEND:-1}" != "0" ]]; then
  stop_from_pid "$LOGDIR/watch-backend.pid"
  start_bg watch-backend "$ROOT" "bash scripts/watch-backend.sh" "$LOGDIR" "$ENV_FILE"
  echo "[OK] Backend watchdog (auto-restart on crash)"
fi
if [[ "${WATCH_AI_INGEST:-1}" != "0" ]]; then
  stop_from_pid "$LOGDIR/watch-ai-ingest.pid"
  start_bg watch-ai-ingest "$ROOT" "bash scripts/watch-ai-ingest.sh" "$LOGDIR" "$ENV_FILE"
  echo "[OK] AI ingest watchdog (auto-restart if frozen)"
fi
