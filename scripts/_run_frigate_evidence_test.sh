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
python3 -c "import yaml;d=yaml.safe_load(open('$ROOT/infra/frigate-config/config.yml'));c=d['cameras']['cv_d2eb7076-c3b3-40fd-9b2c-0d119bb975c9'];print('record',c['record']);print('snapshots',c['snapshots'])"
docker restart citevision-v2-frigate
sleep 30
curl -sf http://127.0.0.1:5000/api/version && echo
cp "$WIN/ai-engine/src/citevision_ai/evidence/service.py" "$ROOT/ai-engine/src/citevision_ai/evidence/service.py"
pkill -f 'uvicorn citevision_ai.main' 2>/dev/null || true
sleep 2
start_bg ai-engine "$ROOT/ai-engine" ".venv/bin/uvicorn citevision_ai.main:app --host 0.0.0.0 --port 8001" "$ROOT/logs" "$ROOT/.env"
sleep 10
python3 "$WIN/scripts/_test_frigate_evidence_live.py"
echo "--- recent DB ---"
python3 "$WIN/scripts/_inspect_evidence_108.py" | head -3
