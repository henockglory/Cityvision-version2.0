#!/usr/bin/env bash
echo "dedupe skips:" $(grep -c 'speed evidence dedupe skip' /home/gheno/citevision-v2/logs/ai-engine.log || echo 0)
echo "sem timeouts recent:" $(tail -n 5000 /home/gheno/citevision-v2/logs/ai-engine.log | grep -c 'evidence semaphore timeout' || echo 0)
echo "frigate_track ok:" $(tail -n 5000 /home/gheno/citevision-v2/logs/ai-engine.log | grep -c 'capture_source=frigate\|frigate_track' || echo 0)
tail -n 3000 /home/gheno/citevision-v2/logs/ai-engine.log | grep -E 'speed evidence dedupe|frigate_track:|semaphore timeout|uploaded|package ready' | tail -25
echo "--- alerts ---"
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c "
SELECT a.created_at,
  a.evidence_snapshot->'package'->'metadata'->>'capture_source',
  a.evidence_snapshot->'completeness'->>'status'
FROM alerts a
WHERE a.org_id='74d51ead-97a7-4e41-a488-503a9b90c466'::uuid
  AND a.created_at > now() - interval '15 minutes'
ORDER BY a.created_at DESC LIMIT 5;
"
echo "--- rules suppressed ---"
tail -n 2000 /home/gheno/citevision-v2/logs/rules-engine.log | grep -E 'incomplete_evidence|alert created|speeding' | tail -15
