#!/usr/bin/env bash
set -uo pipefail
# Stack health for visual demo at :5174 — no zone writes.
ROOT=~/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

echo "=== dockerd ==="
if ! docker info >/dev/null 2>&1; then
  bash /mnt/c/Users/gheno/citevision/scripts/_start_dockerd_wsl.sh || true
fi
docker ps --format '{{.Names}} {{.Status}}' | head -15

echo "=== ports ==="
ss -ltn 2>/dev/null | grep -E '5174|8081|8001|5000|5433|1984' || netstat -ltn 2>/dev/null | grep -E '5174|8081|8001|5000|5433' || true

echo "=== http ==="
for u in \
  http://127.0.0.1:5174/ \
  http://127.0.0.1:8081/health \
  http://127.0.0.1:8001/health \
  http://127.0.0.1:5000/api/version
do
  if curl -sf --max-time 4 "$u" >/dev/null; then
    echo "OK $u"
  else
    echo "DOWN $u"
  fi
done

# Ensure infra containers
for c in citevision-v2-postgres citevision-v2-minio citevision-v2-frigate citevision-v2-go2rtc citevision-v2-mosquitto citevision-v2-redis citevision-v2-mailhog; do
  docker start "$c" >/dev/null 2>&1 || true
done

# Backend / AI / rules if down
if ! curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null; then
  free_port 8081 || true
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$ROOT/logs" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 90 || true
fi
if ! curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null; then
  bash scripts/restart-ai-engine.sh || true
fi
if ! curl -sf --max-time 3 http://127.0.0.1:8010/health >/dev/null; then
  bash scripts/_start-rules-engine.sh || true
fi

echo "=== final ==="
for u in http://127.0.0.1:5174/ http://127.0.0.1:8081/health http://127.0.0.1:8001/health http://127.0.0.1:5000/api/version; do
  curl -sf --max-time 4 "$u" >/dev/null && echo "OK $u" || echo "DOWN $u"
done
echo "UI: http://127.0.0.1:5174/"
