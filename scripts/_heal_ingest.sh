#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2
source scripts/lib/env-utils.sh
load_dotenv .env
KEY="${INTERNAL_API_KEY}"
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild
echo
curl -sf -X POST -H "X-Internal-Key: $KEY" "http://127.0.0.1:8081/api/v1/internal/supervisor/repair?issue=ai_engine"
echo
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams
echo
sleep 25
curl -sf http://127.0.0.1:8001/cameras | python3 -m json.tool | head -40
