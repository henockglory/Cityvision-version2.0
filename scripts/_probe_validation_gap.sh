#!/usr/bin/env bash
set -uo pipefail
echo "=== recent speeding events ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
"SELECT e.event_type, e.created_at, left(e.id::text,8) eid,
  coalesce(e.payload->>'speed_kmh', e.payload->'metadata'->>'speed_kmh','') speed
 FROM events e
 WHERE e.org_id='74d51ead-97a7-4e41-a488-503a9b90c466'::uuid
   AND e.created_at > now() - interval '15 minutes'
 ORDER BY e.created_at DESC LIMIT 15;"

echo "=== recent alerts ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
"SELECT a.created_at, left(a.id::text,8), coalesce(r.name,''),
  left(coalesce(a.evidence_snapshot->'package'->>'evidence_status',''),20)
 FROM alerts a LEFT JOIN rules r ON r.id=a.rule_id
 WHERE a.org_id='74d51ead-97a7-4e41-a488-503a9b90c466'::uuid
   AND a.created_at > now() - interval '30 minutes'
 ORDER BY a.created_at DESC LIMIT 10;"

echo "=== enabled rules ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
"SELECT left(id::text,8), name, is_enabled FROM rules
 WHERE org_id='74d51ead-97a7-4e41-a488-503a9b90c466'::uuid
 ORDER BY name;"

echo "=== rules-engine ==="
curl -sf http://127.0.0.1:8010/health; echo
tail -20 /home/gheno/citevision-v2/logs/rules-engine.log | head -20
