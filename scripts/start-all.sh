#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a && source .env && set +a
fi

echo "==> Starting infrastructure (v2 ports)"
docker compose -f infra/docker-compose.yml up -d

echo "==> Starting AI engine on port ${AI_ENGINE_PORT:-8001}"
# shellcheck disable=SC1091
source ai-engine/.venv/bin/activate 2>/dev/null || true
cd ai-engine
PYTHONPATH=src uvicorn citevision_ai.main:app --host "${AI_ENGINE_HOST:-0.0.0.0}" --port "${AI_ENGINE_PORT:-8001}" &
echo $! > ../logs/ai-engine.pid
cd "$ROOT"

echo "==> Services started. AI PID: $(cat logs/ai-engine.pid 2>/dev/null || echo n/a)"
