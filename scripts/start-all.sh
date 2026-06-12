#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Starting Citévision 2.0 stack"

docker compose up -d

if [ -f "ai-engine/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source ai-engine/.venv/bin/activate
  nohup python -m uvicorn citevision_ai.main:app --host 0.0.0.0 --port 8000 \
    > logs/ai-engine.log 2>&1 &
  echo $! > logs/ai-engine.pid
  echo "AI Engine started (PID $(cat logs/ai-engine.pid))"
fi

echo "==> Stack started. AI Engine: http://localhost:8000/health"
