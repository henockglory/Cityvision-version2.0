#!/usr/bin/env bash
set -euo pipefail
echo "=== start docker ==="
sudo service docker start 2>/dev/null || true
# Docker Desktop on Windows often provides the engine
for i in $(seq 1 30); do
  if docker info >/dev/null 2>&1; then
    echo "docker_ok after ${i}s"
    break
  fi
  echo "wait $i"
  sleep 5
done
docker info >/dev/null

echo "=== verify purge ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT 'alerts', count(*) FROM alerts UNION ALL SELECT 'events', count(*) FROM events;" \
  || { echo "postgres starting..."; sleep 15; docker start citevision-v2-postgres 2>/dev/null || true; sleep 10;
       docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
         "SELECT 'alerts', count(*) FROM alerts UNION ALL SELECT 'events', count(*) FROM events;"; }

docker start citevision-v2-minio 2>/dev/null || true
sleep 3
docker exec citevision-v2-minio du -sh /data/citevision-evidence 2>/dev/null || echo "minio_evidence=?"

docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "UPDATE rules SET is_enabled=false, updated_at=NOW() WHERE name LIKE 'Démo%';"
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT name, is_enabled FROM rules WHERE name LIKE 'Démo%' ORDER BY name;"
echo "=== done ==="
