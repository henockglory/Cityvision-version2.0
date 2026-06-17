#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source "$ROOT/scripts/lib/env-utils.sh"
source "$ROOT/scripts/lib/cuda-utils.sh"
sed -i 's|YOLO_MODEL_PATH=ai-engine/models/yolov8n.onnx|YOLO_MODEL_PATH=models/yolov8n.onnx|' .env 2>/dev/null || true
install_ai_cuda_deps "$ROOT/ai-engine/.venv/bin/pip"
setup_cuda_library_path "$ROOT/ai-engine/.venv/bin/python3"
stop_from_pid "$ROOT/logs/ai-engine.pid"
free_port 8001
sleep 1
UVICORN="$ROOT/ai-engine/.venv/bin/uvicorn"
start_bg ai-engine "$ROOT/ai-engine" "E2E_MODE=1 LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-} $UVICORN citevision_ai.main:app --host 0.0.0.0 --port 8001" "$ROOT/logs" "$ROOT/.env"
HEALTH_WAIT="${AI_HEALTH_WAIT_SECS:-240}"
if wait_http_ok "http://localhost:8001/health" "$HEALTH_WAIT"; then
  curl -sf http://localhost:8001/health | python3 -m json.tool
else
  echo "[FAIL] AI engine health — tail logs/ai-engine.log" >&2
  tail -20 "$ROOT/logs/ai-engine.log" >&2
  exit 1
fi
