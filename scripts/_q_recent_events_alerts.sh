#!/usr/bin/env bash
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT event_type, count(*) FROM events 
WHERE org_id='74d51ead-97a7-4e41-a488-503a9b90c466'::uuid 
  AND created_at > now() - interval '2 hours'
GROUP BY event_type ORDER BY count DESC;
"
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT title, created_at, metadata->>'event_type' as et, metadata->'evidence_snapshot' IS NOT NULL as has_ev
FROM alerts 
WHERE org_id='74d51ead-97a7-4e41-a488-503a9b90c466'::uuid 
  AND created_at > now() - interval '2 hours'
ORDER BY created_at DESC LIMIT 10;
"
