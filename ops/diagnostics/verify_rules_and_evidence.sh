#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
export PATH="$PATH:/usr/local/go/bin:$HOME/go/bin"

echo "=== enabled rules ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT id::text, name, is_enabled, left(definition::text,120) FROM rules WHERE is_enabled;"

echo "=== start rules properly ==="
pkill -f 'rules-engine' 2>/dev/null || true
sleep 1
bash scripts/_start-rules-engine.sh 2>&1 | tail -15
sleep 3
curl -sf http://127.0.0.1:8010/health; echo
tail -20 logs/rules-engine.log 2>/dev/null || true

echo "=== AI health + cameras registered? ==="
curl -sf http://127.0.0.1:8001/health | head -c 200; echo
grep -a -E "camera.*start|ingest|spatial|red_light|speeding" logs/ai-engine.log | tail -15

echo "=== Frigate recent events cam108 ==="
python3 - <<'PY'
import json,urllib.request,time
cam="cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"
now=time.time()
with urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={cam}&limit=8&include_thumbnails=0", timeout=8) as r:
    evs=json.loads(r.read().decode())
print("now", now, "n", len(evs))
for e in evs[:8]:
    s,e2=e.get("start_time"), e.get("end_time")
    age = (now - e2) if isinstance(e2,(int,float)) else None
    print(str(e.get("id"))[:22], e.get("label"), "dur", (e2-s) if e2 and s else None, "age_end", age)
PY

echo "=== recent events DB ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT ingested_at, event_type,
  COALESCE(payload->>'evidence_status','null') AS st,
  COALESCE(payload->>'abort_reason','?') AS abort
FROM events
WHERE ingested_at > now() - interval '15 minutes'
ORDER BY ingested_at DESC LIMIT 15;
"

echo "=== wait 2 min more ==="
sleep 120
echo "=== fresh correlate logs ==="
grep -a -E "accept active|bound capture|no correlated|skip demo|frigate capture missing" logs/ai-engine.log | tail -20
echo "=== DB again ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT event_type,
  COALESCE(payload->>'evidence_status','null') AS st,
  COALESCE(payload->>'abort_reason', payload->'evidence_meta'->>'abort_reason','?') AS reason,
  count(*)
FROM events
WHERE ingested_at > now() - interval '15 minutes'
  AND event_type IN ('red_light_violation','speeding')
GROUP BY 1,2,3 ORDER BY 4 DESC;
"
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT count(*) AS alerts_15m FROM alerts WHERE created_at > now() - interval '15 minutes';
"
