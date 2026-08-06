#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
curl -sf -X POST -H "X-Internal-Key: ${KEY}" \
  http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild
echo
sleep 20
curl -sf http://127.0.0.1:5000/api/stats | python3 -m json.tool | head -25
