#!/usr/bin/env bash
set -euo pipefail
echo "=== start docker (native WSL) ==="
sudo service docker start 2>/dev/null || sudo systemctl start docker 2>/dev/null || true
for i in $(seq 1 40); do
  if docker info >/dev/null 2>&1; then
    echo "docker_ok after ${i}s"
    break
  fi
  echo "wait $i"
  sleep 2
done
docker info >/dev/null
echo "=== start stack containers ==="
cd /home/gheno/citevision-v2
# Prefer compose project already defined
docker start citevision-v2-postgres citevision-v2-minio citevision-v2-frigate citevision-v2-go2rtc citevision-v2-mqtt 2>/dev/null || true
# wait postgres
for i in $(seq 1 30); do
  if docker exec citevision-v2-postgres pg_isready -U citevision >/dev/null 2>&1; then
    echo "postgres_ok"
    break
  fi
  sleep 2
done
docker ps --format '{{.Names}} {{.Status}}' | head -25
