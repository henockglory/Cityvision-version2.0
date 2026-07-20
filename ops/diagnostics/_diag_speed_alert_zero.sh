#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
LOG=$ROOT/logs/ai-engine.log
echo "=== counts since AI start ==="
grep -c 'speed evidence dedupe skip' "$LOG" || true
grep -c 'evidence semaphore timeout' "$LOG" || true
grep -c 'frigate_track:' "$LOG" || true
grep -c 'capture_source\|frigate_track success\|uploaded evidence\|package ready' "$LOG" || true
echo "=== recent relevant ==="
grep -E 'speed evidence dedupe|frigate_track:|semaphore timeout|strict_frigate|IncompleteRead|attach failed|evidence package|upload' "$LOG" | tail -50
echo "=== rules suppressed ==="
grep -E 'incomplete_evidence|suppressed|evidence/request' "$ROOT/logs/rules-engine.log" | tail -20
echo "=== recent events evidence_status ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c "
SELECT e.payload->>'evidence_status', e.payload->'evidence_package'->'metadata'->>'capture_source', count(*)
FROM events e JOIN cameras c ON c.id=e.camera_id
WHERE c.org_id='74d51ead-97a7-4e41-a488-503a9b90c466'::uuid
  AND e.event_type='speeding'
  AND e.ingested_at > now() - interval '15 minutes'
GROUP BY 1,2 ORDER BY 3 DESC;
"
