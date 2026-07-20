#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT/infra"

# Fix stale network: remove old container and recreate
docker rm -f citevision-v2-ocr 2>/dev/null || true
docker compose --env-file "$ROOT/.env" --profile ocr up -d --force-recreate citevision-ocr

echo "waiting OCR..."
for i in $(seq 1 90); do
  st=$(docker inspect citevision-v2-ocr --format '{{.State.Status}}' 2>/dev/null || echo missing)
  if curl -sf --max-time 5 http://127.0.0.1:8181/healthz >/dev/null 2>&1; then
    echo "OCR READY after ${i} attempts status=$st"
    curl -sf http://127.0.0.1:8181/healthz; echo
    exit 0
  fi
  if [[ "$st" == "exited" ]]; then
    echo "OCR exited — logs:"
    docker logs citevision-v2-ocr --tail 50
    exit 1
  fi
  echo "t=$i status=$st"
  sleep 5
done
echo TIMEOUT
docker logs citevision-v2-ocr --tail 80
exit 1
