#!/usr/bin/env bash
# Start AI engine — CUDA 12 libs only (no cu13 from torch in LD_LIBRARY_PATH).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
# shellcheck source=scripts/lib/cuda-utils.sh
source "$ROOT/scripts/lib/cuda-utils.sh"

ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
AI_PORT="${AI_ENGINE_PORT:-8001}"
VENV_PY="${ROOT}/ai-engine/.venv/bin/python3"
VENV_UV="${ROOT}/ai-engine/.venv/bin/uvicorn"

setup_cuda_library_path "$VENV_PY"
export YOLO_DEVICE="${YOLO_DEVICE:-cuda}"
export FLAGS_use_mkldnn=0
export FLAGS_use_onednn=0
export FLAGS_enable_pir_api=0
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

if [[ "${AI_SKIP_VERIFY:-0}" != "1" ]]; then
  VERIFY_ARGS=(--device "$YOLO_DEVICE")
  [[ "${AI_ALLOW_CPU:-0}" == "1" ]] && VERIFY_ARGS+=(--allow-cpu)
  if ! "$VENV_PY" "$ROOT/ai-engine/scripts/verify_ai_stack.py" "${VERIFY_ARGS[@]}"; then
    echo "[FAIL] AI stack not verified — run: bash scripts/install-ai-models.sh --fix" >&2
    echo "       (or AI_SKIP_VERIFY=1 to bypass — not recommended)" >&2
    exit 1
  fi
fi

cd "$ROOT/ai-engine"
exec env LD_LIBRARY_PATH="$LD_LIBRARY_PATH" "$VENV_UV" citevision_ai.main:app --host 0.0.0.0 --port "$AI_PORT"
