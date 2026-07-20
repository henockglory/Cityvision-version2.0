#!/usr/bin/env bash
set -euo pipefail
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT 'alerts', count(*) FROM alerts UNION ALL SELECT 'events', count(*) FROM events;"
docker exec citevision-v2-minio du -sh /data/citevision-evidence 2>/dev/null || echo "minio=?"
# frigate rec size
docker run --rm -v infra_frigate_recordings:/v:ro alpine du -sh /v 2>/dev/null || echo "frigate_vol=?"
