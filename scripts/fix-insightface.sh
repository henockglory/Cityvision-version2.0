#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
rm -rf ai-engine/models/insightface/models/buffalo_l "${HOME}/.insightface/models/buffalo_l"
"${ROOT}/ai-engine/.venv/bin/python" - <<'PY'
from pathlib import Path
from insightface.app import FaceAnalysis
root = Path(".")
app = FaceAnalysis(name="buffalo_l", root=str(root / "ai-engine" / "models" / "insightface"))
app.prepare(ctx_id=-1)
print("[OK] buffalo_l ready")
PY
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
LOGDIR="$ROOT/logs"
AI_PORT="${AI_ENGINE_PORT:-8001}"
stop_from_pid "$LOGDIR/ai-engine.pid" 2>/dev/null || true
free_port "$AI_PORT"
# shellcheck source=scripts/lib/cuda-utils.sh
source "$ROOT/scripts/lib/cuda-utils.sh"
setup_cuda_library_path "${ROOT}/ai-engine/.venv/bin/python3"
start_bg ai-engine "$ROOT/ai-engine" \
  "LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-} ${ROOT}/ai-engine/.venv/bin/uvicorn citevision_ai.main:app --host 0.0.0.0 --port $AI_PORT" \
  "$LOGDIR" "$ENV_FILE"
for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:$AI_PORT/health" | grep -q '"face_loaded":"true"'; then
    curl -sf "http://127.0.0.1:$AI_PORT/health" | python3 -m json.tool
    exit 0
  fi
  sleep 2
done
echo "[WARN] face_loaded still false"
curl -sf "http://127.0.0.1:$AI_PORT/health" | python3 -m json.tool || true
exit 1
