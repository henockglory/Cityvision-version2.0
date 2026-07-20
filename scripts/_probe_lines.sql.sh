#!/usr/bin/env bash
set -uo pipefail
docker exec citevision-v2-postgres psql -U citevision -d citevision -c '\d lines' | head -40
echo '--- lines counting cam ---'
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "SELECT id, name, is_active, camera_id FROM lines WHERE camera_id='9a3cd323-3820-46f0-aa5b-86c086a4a782'::uuid;"
echo '--- line_counters ---'
docker exec citevision-v2-postgres psql -U citevision -d citevision -c '\dt *count*'
docker exec citevision-v2-postgres psql -U citevision -d citevision -c 'SELECT * FROM line_counters ORDER BY 1 DESC LIMIT 10;' 2>&1 | head -30
echo '--- recent line_cross ---'
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "SELECT event_type, left(camera_id::text,8), ingested_at FROM events WHERE event_type='line_cross' ORDER BY ingested_at DESC LIMIT 10;"
