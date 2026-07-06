#!/usr/bin/env bash
set -euo pipefail
cd /home/gheno/citevision-v2
source scripts/lib/env-utils.sh
stop_from_pid logs/ai-engine.pid 2>/dev/null || true
pkill -f 'uvicorn citevision_ai.main' 2>/dev/null || true
free_port 8001 2>/dev/null || true
sleep 2
ENV_FILE="$(ensure_env_file .)"
start_bg ai-engine . "bash scripts/run-ai-engine.sh" logs "$ENV_FILE"
sleep 25
curl -s http://127.0.0.1:8001/health
echo
ai-engine/.venv/bin/python3 ai-engine/scripts/check_ai_health.py --require-gpu
