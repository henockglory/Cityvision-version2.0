#!/usr/bin/env bash
set -euo pipefail
echo "=== post-compact verify ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT 'alerts', count(*) FROM alerts UNION ALL SELECT 'events', count(*) FROM events;"
docker exec citevision-v2-minio du -sh /data/citevision-evidence 2>/dev/null || echo "minio_down"
docker run --rm -v infra_frigate_recordings:/v:ro alpine du -sh /v 2>/dev/null || echo "frigate_vol_?"
# keep demo rules OFF until feu fix
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "UPDATE rules SET is_enabled=false, updated_at=NOW() WHERE name LIKE 'Démo%';"
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT name, is_enabled FROM rules WHERE name LIKE 'Démo%' ORDER BY name;"
echo "=== done ==="
