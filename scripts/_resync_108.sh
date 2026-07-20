#!/usr/bin/env bash
set -euo pipefail
source ~/citevision-v2/scripts/lib/env-utils.sh
load_dotenv ~/citevision-v2/.env
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial" -H "X-Internal-Key: ${KEY}"
echo "[OK] resync-spatial"
sleep 10
curl -s "http://127.0.0.1:8081/api/v1/internal/ingest/orgs/74d51ead-97a7-4e41-a488-503a9b90c466/cameras/37c7d7fa-12dc-450c-8c4b-ab63ed43a819/spatial-config" \
  -H "X-Internal-Key: ${KEY}" | python3 -m json.tool
