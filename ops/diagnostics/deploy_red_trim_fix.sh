#!/usr/bin/env bash
set -euo pipefail
WIN=/mnt/c/Users/gheno/citevision
WSL=/home/gheno/citevision-v2
rsync -a --checksum \
  "$WIN/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py" \
  "$WIN/ai-engine/src/citevision_ai/evidence/service.py" \
  "$WSL/ai-engine/src/citevision_ai/evidence/"
rsync -a --checksum \
  "$WIN/ai-engine/src/citevision_ai/config.py" \
  "$WSL/ai-engine/src/citevision_ai/config.py"
cd "$WSL/ai-engine"
. .venv/bin/activate
python -m pytest tests/test_zone_binding_evidence.py -q --tb=line
bash "$WSL/scripts/_quick_restart_ai.sh"
sleep 10
curl -sf http://127.0.0.1:8001/health | head -c 120; echo
echo "waiting 150s for red-phase evidence..."
sleep 150
echo "=== LOG ==="
grep -a -E "red_light scene from clip|accept active|scene_green|evidence_status|bound capture|complete" \
  /home/gheno/citevision-v2/logs/ai-engine.log | tail -40
echo "=== DB ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT event_type,
  COALESCE(payload->>'evidence_status','null') AS st,
  COALESCE(payload->>'abort_reason', payload->'evidence_meta'->>'abort_reason','?') AS reason,
  count(*)
FROM events
WHERE ingested_at > now() - interval '10 minutes'
  AND event_type IN ('red_light_violation','speeding')
GROUP BY 1,2,3 ORDER BY 4 DESC;
"
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT count(*) AS alerts_10m FROM alerts WHERE created_at > now() - interval '10 minutes';
"
grep -a "alert suppressed\|alert fired\|Alert created\|executed" /home/gheno/citevision-v2/logs/rules-engine.log | tail -15
