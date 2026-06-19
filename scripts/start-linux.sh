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

echo "=== Citevision v2 Start (Linux/WSL) ==="
echo ""

ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

if ! docker info >/dev/null 2>&1; then
  echo "[INFO] Starting Docker daemon..."
  if command -v service >/dev/null 2>&1; then
    sudo service docker start || true
  fi
  sleep 2
  if ! docker info >/dev/null 2>&1; then
    echo "[FAIL] Docker not running. Run: sudo service docker start" >&2
    echo "       Or: bash scripts/setup-wsl.sh" >&2
    exit 1
  fi
fi
echo "[OK] Docker ready"

if command -v nvidia-smi >/dev/null 2>&1; then
  echo "[OK] NVIDIA GPU detected:"
  nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || true
else
  echo "[WARN] nvidia-smi not available — AI will fall back to CPU (see docs/GPU-WSL2.md)"
fi

echo "[INFO] Starting infrastructure..."
bash "$ROOT/scripts/ensure-demo-video.sh"
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

if [[ ! -d ai-engine/.venv ]]; then
  echo "[INFO] Creating AI venv..."
  python3 -m venv ai-engine/.venv
fi
# shellcheck disable=SC1091
source ai-engine/.venv/bin/activate
if ! command -v uvicorn >/dev/null 2>&1 || ! python -c "import citevision_ai" 2>/dev/null; then
  echo "[INFO] Installing AI engine dependencies..."
  pip install -q -e "ai-engine/.[dev]" || pip install -q -e ai-engine/. pytest pytest-asyncio httpx
fi
install_ai_cuda_deps "$ROOT/ai-engine/.venv/bin/pip"
setup_cuda_library_path "$ROOT/ai-engine/.venv/bin/python3"

# ── Vérifier / télécharger le modèle YOLO avant de démarrer l'AI engine ───
mkdir -p ai-engine/models
# Déterminer le modèle requis selon generated.env (fallback: yolov8n.onnx)
CV_YOLO_MODEL="$(grep '^CV_YOLO_MODEL=' generated.env 2>/dev/null | cut -d= -f2 | tr -d ' \r' || true)"
CV_YOLO_MODEL="${CV_YOLO_MODEL:-yolov8n.onnx}"
YOLO_MODEL_PATH="$ROOT/ai-engine/models/$CV_YOLO_MODEL"
if [[ ! -f "$YOLO_MODEL_PATH" ]]; then
  echo "[INFO] Modèle YOLO manquant ($CV_YOLO_MODEL) — téléchargement automatique..."
  YOLO_MODEL="$CV_YOLO_MODEL" bash "$ROOT/scripts/download-yolo-model.sh" 2>&1 \
    && echo "[OK] Modèle $CV_YOLO_MODEL téléchargé" \
    || echo "[WARN] Téléchargement $CV_YOLO_MODEL échoué — fallback yolov8n.onnx"
  # Fallback ultime : tenter yolov8n si le modèle tier n'a pas pu être téléchargé
  if [[ ! -f "$YOLO_MODEL_PATH" ]] && [[ "$CV_YOLO_MODEL" != "yolov8n.onnx" ]]; then
    if [[ ! -f "$ROOT/ai-engine/models/yolov8n.onnx" ]]; then
      YOLO_MODEL="yolov8n.onnx" bash "$ROOT/scripts/download-yolo-model.sh" 2>&1 || true
    fi
  fi
else
  echo "[OK] Modèle YOLO présent : $CV_YOLO_MODEL"
fi

if [[ ! -d frontend/node_modules ]]; then
  echo "[INFO] npm install..."
  (cd frontend && npm install --silent)
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

bash "$ROOT/scripts/ensure-rules-sync-env.sh"
load_dotenv "$ENV_FILE"

start_bg backend "$ROOT/backend" "$GO_BIN run ./cmd/api" "$LOGDIR" "$ENV_FILE"
sleep 3
start_bg rules-engine "$ROOT/rules-engine" "$GO_BIN run ./cmd/rules-engine" "$LOGDIR" "$ENV_FILE"
start_bg ai-engine "$ROOT/ai-engine" "LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-} $ROOT/ai-engine/.venv/bin/uvicorn citevision_ai.main:app --host 0.0.0.0 --port $AI_PORT" "$LOGDIR" "$ENV_FILE"
free_port 5174 5175 5176 5177
sleep 1
start_bg frontend "$ROOT/frontend" "npm run dev -- --host 0.0.0.0 --port 5174 --strictPort" "$LOGDIR" "$ENV_FILE"

echo ""
echo "[INFO] Waiting for backend (first run may download Go modules)..."
if wait_http_ok "http://localhost:$BACKEND_PORT/health" 120; then
  echo "[OK] Backend healthy"
else
  echo "[WARN] Backend timeout - see logs/backend.log"
fi

echo ""
echo "[INFO] Waiting for AI Engine (first run compiles ONNX session)..."
if wait_http_ok "http://localhost:$AI_PORT/health" 120; then
  echo "[OK] AI Engine healthy — http://localhost:$AI_PORT"
  # Vérifier que YOLO est réellement chargé
  YOLO_STATUS="$(curl -sf "http://localhost:$AI_PORT/health" 2>/dev/null \
    | grep -o '"yolo_loaded":"[^"]*"' | cut -d'"' -f4 || echo "unknown")"
  if [[ "$YOLO_STATUS" == "true" ]]; then
    echo "[OK] YOLO model chargé et opérationnel — inférence vidéo active"
  else
    echo "[WARN] AI Engine up mais YOLO non chargé (yolo_loaded=$YOLO_STATUS)"
    echo "       Tentative de téléchargement du modèle à chaud..."
    YOLO_MODEL="${CV_YOLO_MODEL:-yolov8n.onnx}" bash "$ROOT/scripts/download-yolo-model.sh" 2>&1 | tail -3 || true
    echo "       Redémarrez l'AI Engine si le modèle vient d'être téléchargé :"
    echo "       pkill -f uvicorn && bash scripts/start-linux.sh"
  fi
else
  echo "[WARN] AI Engine non joignable après 120s — vérifiez logs/ai-engine.log"
  echo "       Règles de détection vidéo désactivées jusqu'au démarrage de l'AI Engine"
fi

echo ""
echo "[INFO] Waiting for Rules Engine..."
if wait_http_ok "http://localhost:$RULES_PORT/health" 30; then
  echo "[OK] Rules Engine healthy — http://localhost:$RULES_PORT"
else
  echo "[WARN] Rules Engine timeout - see logs/rules-engine.log"
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
