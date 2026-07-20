#!/usr/bin/env bash
set -euo pipefail
export PATH="$PATH:/usr/local/go/bin"
ROOT=~/citevision-v2
source "$ROOT/scripts/lib/env-utils.sh"
pkill -f citevision-api 2>/dev/null || true
sleep 2
start_bg backend "$ROOT" "$ROOT/backend/bin/citevision-api" "$ROOT/logs" "$ROOT/.env"
sleep 8
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild" \
  -H "X-Internal-Key: changeme_internal_service_key"
echo
python3 -c "
import yaml
p='$ROOT/infra/frigate-config/config.yml'
d=yaml.safe_load(open(p))
cam=d['cameras']['cv_d2eb7076-c3b3-40fd-9b2c-0d119bb975c9']
print('record', cam.get('record'))
print('snapshots', cam.get('snapshots'))
"
docker restart citevision-v2-frigate
sleep 20
curl -sf http://127.0.0.1:8081/health/frigate
echo
