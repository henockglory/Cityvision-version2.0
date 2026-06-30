#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
# shellcheck source=scripts/lib/cuda-utils.sh
source "$ROOT/scripts/lib/cuda-utils.sh"

ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
LOGDIR="$ROOT/logs"
AI_PORT="${AI_ENGINE_PORT:-8001}"

echo "==> Fix InsightFace buffalo_l empty directory"
rm -rf ai-engine/models/insightface/models/buffalo_l "${HOME}/.insightface/models/buffalo_l"
"${ROOT}/ai-engine/.venv/bin/python" - <<PY
from pathlib import Path
from insightface.app import FaceAnalysis
root = Path("${ROOT}")
app = FaceAnalysis(name="buffalo_l", root=str(root / "ai-engine" / "models" / "insightface"))
app.prepare(ctx_id=-1)
print("[OK] buffalo_l downloaded")
PY

echo "==> Restart AI engine"
stop_from_pid "$LOGDIR/ai-engine.pid"
free_port "$AI_PORT"
sleep 2
setup_cuda_library_path "${ROOT}/ai-engine/.venv/bin/python3"
start_bg ai-engine "$ROOT/ai-engine" \
  "LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-} ${ROOT}/ai-engine/.venv/bin/uvicorn citevision_ai.main:app --host 0.0.0.0 --port $AI_PORT" \
  "$LOGDIR" "$ENV_FILE"

for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:$AI_PORT/health" | grep -q '"face_loaded":"true"'; then
    echo "[OK] AI health gate passed"
    break
  fi
  sleep 2
done
curl -sf "http://127.0.0.1:$AI_PORT/health" || true
echo

echo "==> Start frontend if not running"
if ! curl -sf http://localhost:5174/ >/dev/null 2>&1; then
  free_port 5174 5175 5176 5177
  start_bg frontend "$ROOT/frontend" "npm run dev -- --host 0.0.0.0 --port 5174 --strictPort" "$LOGDIR" "$ENV_FILE"
  for _ in $(seq 1 45); do
    if curl -sf http://localhost:5174/ >/dev/null 2>&1; then
      echo "[OK] frontend up"
      break
    fi
    sleep 2
  done
else
  echo "[OK] frontend already up"
fi

echo "==> Seed demo rules"
cd "$ROOT/backend"
GO_BIN="/usr/local/go/bin/go"
[[ -x "$GO_BIN" ]] || GO_BIN="$(command -v go)"
set -a
# shellcheck disable=SC1091
source "$ENV_FILE"
set +a
"$GO_BIN" run ./cmd/seed-demo-rules

echo "=== Resume complete ==="
