#!/usr/bin/env bash
set -euo pipefail
export PATH="$PATH:/usr/local/go/bin"
WIN=/mnt/c/Users/gheno/citevision
ROOT=~/citevision-v2
cp "$WIN/backend/internal/frigate/compiler.go" "$ROOT/backend/internal/frigate/compiler.go"
cd "$ROOT/backend" && go build -o bin/citevision-api ./cmd/api
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild" \
  -H "X-Internal-Key: changeme_internal_service_key"
echo
grep -A6 'record:' "$ROOT/infra/frigate-config/config.yml" | head -8
docker restart citevision-v2-frigate
echo DONE
