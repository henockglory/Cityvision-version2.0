#!/usr/bin/env bash
set -euo pipefail
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT a.id::text, a.created_at::text, a.evidence_snapshot->'package'->'metadata'->>'evidence_status', a.evidence_snapshot->'package'->'metadata'->>'missing_roles' FROM alerts a JOIN rules r ON r.id=a.rule_id WHERE r.name LIKE '%Feu%' ORDER BY a.created_at DESC LIMIT 5;"
