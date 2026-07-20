#!/usr/bin/env bash
set -uo pipefail
ROOT=~/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
LOGDIR="$ROOT/logs"

echo "UI before: $(curl -sf --max-time 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:5174/ || echo DOWN)"

# dockerd + postgres
if ! docker info >/dev/null 2>&1; then
  bash /mnt/c/Users/gheno/citevision/scripts/_start_dockerd_wsl.sh || true
fi
docker start citevision-v2-postgres citevision-v2-minio citevision-v2-frigate citevision-v2-go2rtc citevision-v2-mosquitto citevision-v2-redis citevision-v2-mailhog >/dev/null 2>&1 || true
for i in $(seq 1 20); do
  docker exec citevision-v2-postgres pg_isready -U citevision >/dev/null 2>&1 && break
  sleep 2
done

# backend
if ! curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null; then
  free_port 8081 || true
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 90 || { echo BE_FAIL; tail -30 "$LOGDIR/backend.log"; }
fi
echo "backend: $(curl -sf --max-time 3 http://127.0.0.1:8081/health || echo DOWN)"

# AI
if ! curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null; then
  bash scripts/restart-ai-engine.sh || true
  for i in $(seq 1 60); do
    curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null && break
    sleep 2
  done
fi
echo "ai: $(curl -sf --max-time 3 http://127.0.0.1:8001/health | head -c 120 || echo DOWN)"

# rules
if ! curl -sf --max-time 3 http://127.0.0.1:8010/health >/dev/null; then
  bash scripts/_start-rules-engine.sh || true
fi

# NEVER kill vite — only restart if down
if ! curl -sf --max-time 3 http://127.0.0.1:5174/ >/dev/null; then
  echo "UI down — restarting :5174 only"
  bash scripts/_sync_frontend_restart_wsl.sh || true
fi

echo "=== FINAL ==="
echo "UI $(curl -sf --max-time 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:5174/ || echo DOWN) -> http://127.0.0.1:5174/"
curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null && echo BE_OK || echo BE_DOWN
curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null && echo AI_OK || echo AI_DOWN
curl -sf --max-time 3 http://127.0.0.1:5000/api/version >/dev/null && echo FRIGATE_OK || echo FRIGATE_DOWN
