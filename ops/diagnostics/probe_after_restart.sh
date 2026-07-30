#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
bash "$ROOT/scripts/_start_dockerd_wsl.sh" || true
sleep 8
echo "=== DOCKER ==="
docker ps --format '{{.Names}}' 2>&1 | head -20 || true
echo "=== NOW ==="
python3 -c "import time; print(time.time())"
echo "=== FRESH LOG (after restart marker) ==="
# Append a marker by touching a note in log via logger is hard; filter by file mtime / last 20 lines from current process
tail -n 5 "$ROOT/logs/ai-engine.log" | strings | tail -5
echo "=== GREP LAST 25 relevant ==="
grep -a -E "accept active|bound capture|skip demo vehicle|no correlated|frigate capture missing|Started ai-engine" "$ROOT/logs/ai-engine.log" | tail -25
echo "=== DB ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT event_type,
  COALESCE(payload->>'evidence_status','null') AS st,
  COALESCE(payload->>'abort_reason', payload->'evidence_meta'->>'abort_reason','?') AS reason,
  count(*)
FROM citevision.events
WHERE created_at > now() - interval '15 minutes'
  AND event_type IN ('red_light_violation','speeding')
GROUP BY 1,2,3 ORDER BY 4 DESC;
" 2>&1 || true
echo "=== ALERTS ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT count(*) AS alerts_15m FROM citevision.alerts WHERE created_at > now() - interval '15 minutes';
" 2>&1 || true
