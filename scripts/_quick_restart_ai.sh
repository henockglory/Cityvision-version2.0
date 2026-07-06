#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
stop_from_pid "$ROOT/logs/ai-engine.pid" || true
pkill -f 'uvicorn citevision_ai.main' 2>/dev/null || true
free_port 8001 || true
sleep 2
ENV_FILE="$(ensure_env_file "$ROOT")"
mkdir -p "$ROOT/logs"
start_bg ai-engine "$ROOT" "bash scripts/run-ai-engine.sh" "$ROOT/logs" "$ENV_FILE"
sleep 12
curl -sf http://127.0.0.1:8001/health
