#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2
echo "=== ENV ==="
grep -E '^(DEFAULT_ORG_ID|INTERNAL_API_KEY|BACKEND_API_URL)=' .env 2>/dev/null || true
echo "=== RULES ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "SELECT id, name, is_enabled FROM rules ORDER BY name LIMIT 15;"
echo "=== CAMERAS ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "SELECT id, name, is_active, metadata->>'demo_video_id' AS vid FROM cameras WHERE metadata->>'demo' = 'true' ORDER BY name;"
echo "=== ZONES ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "SELECT z.name, c.name AS camera, z.behavior_config FROM zones z JOIN cameras c ON c.id = z.camera_id WHERE c.metadata->>'demo' = 'true' ORDER BY c.name, z.name;"
