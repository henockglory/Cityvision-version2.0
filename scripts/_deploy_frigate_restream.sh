#!/usr/bin/env bash
set -euo pipefail
export PATH="$PATH:/usr/local/go/bin"
WIN=/mnt/c/Users/gheno/citevision
ROOT=~/citevision-v2
cp "$WIN/backend/internal/frigate/compiler.go" "$ROOT/backend/internal/frigate/compiler.go"
cd "$ROOT/backend"
go test ./internal/frigate/... -count=1
go build -o bin/citevision-api ./cmd/api
pkill -f citevision-api 2>/dev/null || true
sleep 2
source "$ROOT/scripts/lib/env-utils.sh"
start_bg backend "$ROOT" "$ROOT/backend/bin/citevision-api" "$ROOT/logs" "$ROOT/.env"
sleep 6
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild" \
  -H "X-Internal-Key: changeme_internal_service_key"
echo
echo "=== go2rtc.streams ==="
grep -A6 'go2rtc:' "$ROOT/infra/frigate-config/config.yml" | head -12
echo "=== camera live ==="
grep -A8 'cv_d2eb7076' "$ROOT/infra/frigate-config/config.yml" | head -20
docker restart citevision-v2-frigate
sleep 25
docker exec citevision-v2-frigate wget -qO- http://127.0.0.1:1984/api/streams 2>&1 | head -c 400
echo
