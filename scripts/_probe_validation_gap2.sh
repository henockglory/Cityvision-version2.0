#!/usr/bin/env bash
set -uo pipefail
ORG=74d51ead-97a7-4e41-a488-503a9b90c466
echo "=== events schema sample ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
"SELECT column_name FROM information_schema.columns WHERE table_name='events' ORDER BY ordinal_position;" | head -40

echo "=== recent events ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
"SELECT e.event_type, e.ingested_at, left(e.id::text,8)
 FROM events e JOIN cameras c ON c.id=e.camera_id
 WHERE c.org_id='$ORG'::uuid AND e.ingested_at > now() - interval '20 minutes'
 ORDER BY e.ingested_at DESC LIMIT 20;"

echo "=== rules ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
"SELECT left(id::text,8)||'|'||name||'|'||is_enabled::text FROM rules WHERE org_id='$ORG'::uuid ORDER BY name;"

echo "=== rules-engine log tail ==="
tail -40 /home/gheno/citevision-v2/logs/rules-engine.log

echo "=== validate log tail ==="
tail -30 /home/gheno/citevision-v2/logs/validate-all-5.log
