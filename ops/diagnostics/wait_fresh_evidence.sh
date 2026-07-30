#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2

for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf http://127.0.0.1:8001/health >/dev/null; then
    echo "AI healthy"
    break
  fi
  sleep 2
done
curl -sf http://127.0.0.1:8001/health | head -c 160 || true
echo
curl -sf http://127.0.0.1:8010/health || echo "rules DOWN"
echo
curl -sf http://127.0.0.1:8081/health || echo "backend DOWN"
echo

echo "waiting 180s for red-phase evidence..."
sleep 180

echo "=== LOG (fresh) ==="
grep -a -E "red_light scene from clip|accept active|scene_green|bound capture|frigate capture missing|no correlated|evidence_abort" \
  "$ROOT/logs/ai-engine.log" | tail -50 || true

echo "=== DB 15m ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT event_type,
  COALESCE(payload->>'evidence_status','null') AS st,
  COALESCE(payload->>'abort_reason', payload->'evidence_meta'->>'abort_reason','?') AS reason,
  count(*)
FROM events
WHERE ingested_at > now() - interval '15 minutes'
  AND event_type IN ('red_light_violation','speeding')
GROUP BY 1,2,3 ORDER BY 4 DESC;
" || true

echo "=== ALERTS ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT count(*) AS alerts_15m FROM alerts WHERE created_at > now() - interval '15 minutes';
" || true

echo "=== RULES ==="
grep -aE "alert suppressed|alert fired|executed|evidence missing|evidence complete" \
  "$ROOT/logs/rules-engine.log" | tail -20 || true

echo "=== code check ==="
grep -n "_trim_clip_bytes_around\|red_frame_from_clip\|BEFORE trim" \
  "$ROOT/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py" | head -10
