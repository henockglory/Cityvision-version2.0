#!/usr/bin/env bash
set -euo pipefail
CONTAINER="${POSTGRES_CONTAINER:-citevision-v2-postgres}"
docker exec "$CONTAINER" psql -U citevision -d citevision <<'SQL'
ALTER TABLE zones ADD COLUMN IF NOT EXISTS zone_kind TEXT NOT NULL DEFAULT '';
SQL
echo "[OK] zone_kind column"
