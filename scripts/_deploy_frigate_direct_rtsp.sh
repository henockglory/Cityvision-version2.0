#!/usr/bin/env bash
set -euo pipefail
export PATH="$PATH:/usr/local/go/bin"
WIN=/mnt/c/Users/gheno/citevision
ROOT=~/citevision-v2
cp "$WIN/backend/internal/frigate/compiler.go" "$ROOT/backend/internal/frigate/compiler.go"
cd "$ROOT/backend" && go build -o bin/citevision-api ./cmd/api
pkill -f citevision-api 2>/dev/null || true
sleep 2
source "$ROOT/scripts/lib/env-utils.sh"
start_bg backend "$ROOT" "$ROOT/backend/bin/citevision-api" "$ROOT/logs" "$ROOT/.env"
sleep 8
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild" \
  -H "X-Internal-Key: changeme_internal_service_key"
echo
grep -A12 'cv_d2eb7076' "$ROOT/infra/frigate-config/config.yml" | head -15
docker restart citevision-v2-frigate
sleep 35
curl -s http://127.0.0.1:5000/api/stats | head -c 400
echo
docker logs citevision-v2-frigate 2>&1 | tail -8
