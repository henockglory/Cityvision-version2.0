#!/usr/bin/env bash
set -euo pipefail

echo "=== Docker volumes (citevision) ==="
docker volume ls 2>/dev/null || { echo "docker unavailable"; exit 0; }

for v in $(docker volume ls -q 2>/dev/null); do
  sz=$(docker run --rm -v "${v}:/v:ro" alpine sh -c 'du -sh /v 2>/dev/null | cut -f1' 2>/dev/null || echo "?")
  echo "  ${v}: ${sz}"
done

echo ""
echo "=== MinIO evidence bucket (if mc available) ==="
if docker ps --format '{{.Names}}' 2>/dev/null | grep -qi minio; then
  docker exec "$(docker ps --format '{{.Names}}' | grep -i minio | head -1)" \
    sh -c 'du -sh /data 2>/dev/null; find /data -type f 2>/dev/null | wc -l' 2>/dev/null || true
fi

echo ""
echo "=== PostgreSQL volume rough size ==="
for v in $(docker volume ls -q 2>/dev/null); do
  if echo "$v" | grep -qi postgres; then
    docker run --rm -v "${v}:/v:ro" alpine sh -c 'du -sh /v 2>/dev/null' 2>/dev/null
  fi
done

echo ""
echo "=== Evidence DB counts ==="
if docker ps --format '{{.Names}}' 2>/dev/null | grep -qi postgres; then
  pg=$(docker ps --format '{{.Names}}' | grep -i postgres | head -1)
  docker exec "$pg" psql -U citevision -d citevision -t -c \
    "SELECT 'evidence_objects', count(*) FROM evidence_objects UNION ALL SELECT 'events', count(*) FROM events UNION ALL SELECT 'alerts', count(*) FROM alerts;" 2>/dev/null || true
fi
