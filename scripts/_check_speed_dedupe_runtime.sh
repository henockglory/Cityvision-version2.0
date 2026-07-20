#!/usr/bin/env bash
set -uo pipefail
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c "
SELECT left(e.payload->>'track_id',12) AS tid, count(*)
FROM events e JOIN cameras c ON c.id=e.camera_id
WHERE c.org_id='74d51ead-97a7-4e41-a488-503a9b90c466'::uuid
  AND e.event_type='speeding'
  AND e.ingested_at > now() - interval '10 minutes'
GROUP BY 1 ORDER BY 2 DESC LIMIT 20;
"
echo "---"
grep -c 'speed evidence dedupe skip' /home/gheno/citevision-v2/logs/ai-engine.log || true
grep -c 'evidence semaphore timeout' /home/gheno/citevision-v2/logs/ai-engine.log || true
# Is running AI process older than service.py?
stat -c '%y %n' /home/gheno/citevision-v2/ai-engine/src/citevision_ai/evidence/service.py
stat -c '%y %n' /home/gheno/citevision-v2/logs/ai-engine.pid 2>/dev/null || true
ps -p "$(cat /home/gheno/citevision-v2/logs/ai-engine.pid 2>/dev/null)" -o lstart=,etime= 2>/dev/null || true
