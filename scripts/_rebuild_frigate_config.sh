#!/usr/bin/env bash
set -euo pipefail
export PATH="$PATH:/usr/local/go/bin"
ROOT=~/citevision-v2
cd "$ROOT/backend"
go build -o bin/citevision-api ./cmd/api
pkill -f citevision-api 2>/dev/null || true
sleep 2
source "$ROOT/scripts/lib/env-utils.sh"
start_bg backend "$ROOT" "$ROOT/backend/bin/citevision-api" "$ROOT/logs" "$ROOT/.env"
sleep 6
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild" \
  -H "X-Internal-Key: changeme_internal_service_key"
echo
grep -A3 'inputs:' "$ROOT/infra/frigate-config/config.yml" | head -8
docker restart citevision-v2-frigate
sleep 20
docker logs citevision-v2-frigate 2>&1 | tail -12
