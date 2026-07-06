#!/bin/bash
set -e
cd ~/citevision-v2
export PATH="$PATH:/usr/local/go/bin"

find scripts -name '*.sh' -exec sed -i 's/\r$//' {} + 2>/dev/null || true

# WSL: pas de systemd — démarrer dockerd si absent
if ! docker info >/dev/null 2>&1; then
  sudo nohup dockerd > /tmp/dockerd.log 2>&1 &
  sleep 4
fi
if ! docker info >/dev/null 2>&1; then
  echo "[FAIL] Docker daemon not running" >&2
  exit 1
fi

source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$PWD")"
load_dotenv "$ENV_FILE"

echo "=== Docker compose up ==="
docker compose -f infra/docker-compose.yml --env-file "$ENV_FILE" up -d
sleep 5
docker ps --format 'table {{.Names}}\t{{.Status}}'
