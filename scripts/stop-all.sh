#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Stopping Citévision 2.0 stack"

if [ -f "logs/ai-engine.pid" ]; then
  PID=$(cat logs/ai-engine.pid)
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" || true
    echo "Stopped AI Engine (PID $PID)"
  fi
  rm -f logs/ai-engine.pid
fi

docker compose down

echo "==> Stack stopped."
