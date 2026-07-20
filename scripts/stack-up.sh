#!/usr/bin/env bash
# Sprint 3 — one-command resume after WSL restart / crash.
# Usage: bash scripts/stack-up.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== CitéVision stack-up $(date -Is) ==="

bash "$ROOT/scripts/_start_dockerd_wsl.sh"

cd "$ROOT/infra"
# Always pass root .env so VIDEOS_PATH mounts the real demo MP4s (not infra/data/videos).
COMPOSE_ENV=(--env-file "$ROOT/.env")
docker compose "${COMPOSE_ENV[@]}" up -d postgres redis mosquitto minio mailhog go2rtc
docker compose "${COMPOSE_ENV[@]}" --profile frigate up -d frigate || true
# OCR required for road evidence plate slot (Sprint 4 / A.3)
docker compose "${COMPOSE_ENV[@]}" --profile ocr up -d citevision-ocr || true

# Heal demo streams if go2rtc empty
if [[ -x "$ROOT/scripts/ensure-demo-streams.sh" ]]; then
  STREAMS="$(curl -sf --max-time 3 http://127.0.0.1:1984/api/streams 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d) if isinstance(d,dict) else 0)' 2>/dev/null || echo 0)"
  if [[ "${STREAMS:-0}" == "0" ]]; then
    echo "go2rtc streams=0 — ensure-demo-streams"
    bash "$ROOT/scripts/ensure-demo-streams.sh" || true
  fi
fi

# AI (single uvicorn)
if [[ -f "$ROOT/scripts/_restart_ai.py" ]]; then
  echo "restart AI..."
  python3 "$ROOT/scripts/_restart_ai.py" || true
fi

# Backend / rules if helpers exist
[[ -f "$ROOT/scripts/_restart_backend.sh" ]] && bash "$ROOT/scripts/_restart_backend.sh" || true
[[ -f "$ROOT/scripts/_start-rules-engine.sh" ]] && bash "$ROOT/scripts/_start-rules-engine.sh" || true

if [[ -x "$ROOT/scripts/health_check_all.sh" ]]; then
  bash "$ROOT/scripts/health_check_all.sh" || {
    echo "stack-up: health not fully green — see above"
    exit 1
  }
fi

echo "=== stack-up OK ==="
echo "UI: start Vite on :5174 if needed (frontend)"
