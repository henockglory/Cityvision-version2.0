#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib/cuda-utils.sh
source "$ROOT/scripts/lib/cuda-utils.sh"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"

ensure_ort_gpu_only "$ROOT/ai-engine/.venv/bin/pip"
stop_from_pid "$ROOT/logs/ai-engine.pid" || true
free_port "${AI_ENGINE_PORT:-8001}" || true
sleep 2
mkdir -p "$ROOT/logs"
ENV_FILE="$(ensure_env_file "$ROOT")"
start_bg ai-engine "$ROOT" "bash scripts/run-ai-engine.sh" "$ROOT/logs" "$ENV_FILE"
sleep 10
curl -sf "http://127.0.0.1:${AI_ENGINE_PORT:-8001}/health" | python3 -m json.tool
