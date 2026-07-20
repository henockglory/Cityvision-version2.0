#!/usr/bin/env bash
set -euo pipefail
export PATH="$PATH:/usr/local/go/bin"
WIN=/mnt/c/Users/gheno/citevision
ROOT=~/citevision-v2
cp "$WIN/infra/docker-compose.yml" "$ROOT/infra/docker-compose.yml"
cp "$WIN/infra/frigate.base.yaml" "$ROOT/infra/frigate.base.yaml"
cp "$WIN/backend/internal/frigate/compiler.go" "$ROOT/backend/internal/frigate/compiler.go"
cp "$WIN/backend/internal/frigate/config.go" "$ROOT/backend/internal/frigate/config.go"
python3 "$WIN/scripts/_enable_frigate_env.py" "$ROOT"
cd "$ROOT/backend" && go build -o bin/citevision-api ./cmd/api
pkill -f citevision-api 2>/dev/null || true
sleep 2
source "$ROOT/scripts/lib/env-utils.sh"
start_bg backend "$ROOT" "$ROOT/backend/bin/citevision-api" "$ROOT/logs" "$ROOT/.env"
sleep 8
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild" \
  -H "X-Internal-Key: changeme_internal_service_key" || true
echo
grep -A3 'go2rtc:' "$ROOT/infra/frigate-config/config.yml" | head -8
cd "$ROOT"
docker compose -f infra/docker-compose.yml --env-file .env --profile frigate up -d frigate --force-recreate
sleep 35
curl -sf http://127.0.0.1:5000/api/version && echo
curl -sf http://127.0.0.1:5000/api/stats 2>/dev/null | head -c 400 && echo
