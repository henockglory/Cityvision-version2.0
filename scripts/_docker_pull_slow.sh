#!/bin/bash
# Pull images une par une (réseau lent) puis démarre la stack
set -euo pipefail
cd ~/citevision-v2
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$PWD")"
load_dotenv "$ENV_FILE"

if ! docker info >/dev/null 2>&1; then
  sudo nohup dockerd > /tmp/dockerd.log 2>&1 &
  sleep 5
fi

export COMPOSE_PARALLEL_LIMIT=1

SERVICES=(postgres redis mosquitto minio mailhog go2rtc)
for svc in "${SERVICES[@]}"; do
  echo "=== Pull $svc ==="
  for attempt in 1 2 3 4 5; do
    if docker compose -f infra/docker-compose.yml --env-file "$ENV_FILE" pull "$svc"; then
      echo "[OK] $svc"
      break
    fi
    echo "[retry $attempt] $svc..."
    sleep 15
  done
done

echo "=== Up ==="
docker compose -f infra/docker-compose.yml --env-file "$ENV_FILE" up -d
sleep 10
docker ps --format 'table {{.Names}}\t{{.Status}}'
