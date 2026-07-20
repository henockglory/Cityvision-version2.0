#!/usr/bin/env bash
set -euo pipefail
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -c "SELECT email FROM users LIMIT 5;"
echo "--- alerts ---"
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "SELECT id, metadata->>'capture_source' as src, created_at FROM alerts WHERE metadata->>'camera_id'='37c7d7fa-12dc-450c-8c4b-ab63ed43a819' ORDER BY created_at DESC LIMIT 10;"
