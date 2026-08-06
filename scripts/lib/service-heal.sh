#!/usr/bin/env bash
# Lightweight service heal — backend / AI / rules-engine (permanent validate path).
set -uo pipefail

ROOT="${CITEVISION_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
API="${BACKEND_API_URL:-http://127.0.0.1:8081}"
AI="${AI_URL:-http://127.0.0.1:8001}"
RULES_PORT="${RULES_ENGINE_PORT:-8010}"

restart_ai_engine() {
  local i
  if [[ -f "$ROOT/scripts/_restart_ai.py" ]]; then
    python3 "$ROOT/scripts/_restart_ai.py" || return 1
  else
    bash "$ROOT/scripts/run-ai-engine.sh" >/dev/null 2>&1 &
  fi
  for i in $(seq 1 20); do
    curl -sf -m 8 "$AI/health" >/dev/null && return 0
    sleep 3
  done
  return 1
}

ensure_backend_up() {
  local wait_sec="${1:-30}"
  local i=0
  while (( i < wait_sec )); do
    if curl -sf -m 5 "$API/health" >/dev/null 2>&1 \
      || curl -sf -m 5 "$API/api/v1/health" >/dev/null 2>&1; then
      return 0
    fi
    if (( i == 0 )) && [[ -f "$ROOT/scripts/_restart_backend.sh" ]]; then
      bash "$ROOT/scripts/_restart_backend.sh" >/dev/null 2>&1 || true
    fi
    sleep 2
    ((i += 2)) || true
  done
  return 1
}

ensure_ai_up() {
  curl -sf -m 8 "$AI/health" >/dev/null && return 0
  restart_ai_engine
}

ensure_rules_engine_up() {
  if curl -sf -m 8 "http://127.0.0.1:${RULES_PORT}/health" >/dev/null 2>&1; then
    return 0
  fi
  if [[ -f "$ROOT/scripts/_start-rules-engine.sh" ]]; then
    bash "$ROOT/scripts/_start-rules-engine.sh" >/dev/null 2>&1 || true
    sleep 5
  fi
  curl -sf -m 8 "http://127.0.0.1:${RULES_PORT}/health" >/dev/null 2>&1
}

ensure_services_healthy() {
  local ok=0
  ensure_backend_up 30 || ok=1
  ensure_ai_up || ok=1
  ensure_rules_engine_up || ok=1
  return "$ok"
}
