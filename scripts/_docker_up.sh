#!/bin/bash
set -e
cd ~/citevision-v2
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$PWD")"
load_dotenv "$ENV_FILE"

if ! docker info >/dev/null 2>&1; then
  sudo nohup dockerd > /tmp/dockerd.log 2>&1 &
  sleep 5
fi

echo "=== docker compose pull (retry) ==="
for i in 1 2 3; do
  if docker compose -f infra/docker-compose.yml --env-file "$ENV_FILE" pull; then
    break
  fi
  echo "Retry $i..."
  sleep 10
done

echo "=== docker compose up ==="
docker compose -f infra/docker-compose.yml --env-file "$ENV_FILE" up -d
sleep 10
docker ps --format 'table {{.Names}}\t{{.Status}}'
