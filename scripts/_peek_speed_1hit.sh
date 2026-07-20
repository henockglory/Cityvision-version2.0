#!/usr/bin/env bash
# Quick peek while 1-hit runs
ROOT=/home/gheno/citevision-v2
echo "=== recent AI evidence lines ==="
grep -E 'speed evidence|frigate_track|semaphore|dropping|attach_evidence|IncompleteRead|capture_source' \
  "$ROOT/logs/ai-engine.log" | tail -40
echo "=== rules-engine suppressed ==="
grep -E 'incomplete_evidence|suppressed|speeding|evidence' "$ROOT/logs/rules-engine.log" | tail -30
echo "=== latest speeding events/alerts ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c "
SELECT e.event_type, e.ingested_at, left(e.id::text,8)
FROM events e JOIN cameras c ON c.id=e.camera_id
WHERE c.org_id='74d51ead-97a7-4e41-a488-503a9b90c466'::uuid
  AND e.event_type='speeding'
ORDER BY e.ingested_at DESC LIMIT 5;
"
echo "--- alerts ---"
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c "
SELECT a.created_at, a.status,
  a.evidence_snapshot->'package'->'metadata'->>'capture_source' AS src,
  a.evidence_snapshot->'package'->'metadata'->>'frigate_event_id' AS fev
FROM alerts a
WHERE a.org_id='74d51ead-97a7-4e41-a488-503a9b90c466'::uuid
ORDER BY a.created_at DESC LIMIT 5;
"
