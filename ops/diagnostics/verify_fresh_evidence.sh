#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
export PATH="$PATH:/usr/local/go/bin:$HOME/go/bin"

echo "=== cameras ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT id::text, name FROM cameras ORDER BY name LIMIT 10;"

echo "=== rules ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT id::text, name, is_enabled, event_type FROM rules LIMIT 20;" 2>&1 || \
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT column_name FROM information_schema.columns WHERE table_name='rules';"

echo "=== seed rules if needed ==="
ENABLED=$(docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT count(*) FROM rules WHERE is_enabled;" 2>/dev/null || echo 0)
echo "enabled_rules=$ENABLED"
if [[ "${ENABLED:-0}" == "0" ]]; then
  bash scripts/seed-demo-rules.sh 2>&1 | tail -30 || true
  bash scripts/seed-demo-spatial.sh 2>&1 | tail -30 || true
fi

echo "=== rules engine ==="
curl -sf http://127.0.0.1:8010/health || echo FAIL
# restart rules to pick up rules
if [[ -x scripts/_start-rules-engine.sh ]]; then
  pkill -f rules-engine 2>/dev/null || true
  sleep 1
  bash scripts/_start-rules-engine.sh 2>&1 | tail -10 || true
  sleep 2
  curl -sf http://127.0.0.1:8010/health; echo
fi

echo "=== truncate old ai log noise — wait 90s for fresh evidence ==="
# Write a unique marker into a side file with timestamp
python3 -c "import time; open('/tmp/cv_probe_mark','w').write(str(time.time()))"
MARK=$(cat /tmp/cv_probe_mark)
echo "mark=$MARK"
sleep 90

echo "=== FRESH LOG after mark (anchors >= mark-60) ==="
python3 - <<'PY'
import time
mark=float(open("/tmp/cv_probe_mark").read())
# show log lines whose wall message is recent: parse nothing; just last 40 matching after file size growth
import subprocess
out=subprocess.check_output(["grep","-a","-E","accept active|bound capture|skip demo|no correlated|frigate capture missing|stale anchor","/home/gheno/citevision-v2/logs/ai-engine.log"], text=True, stderr=subprocess.DEVNULL)
lines=out.strip().splitlines()[-30:]
print("\n".join(lines) if lines else "none")
print("--- now", time.time(), "mark", mark)
PY

echo "=== DB evidence 20m ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT event_type,
  COALESCE(payload->>'evidence_status','null') AS st,
  COALESCE(payload->>'abort_reason', payload->'evidence_meta'->>'abort_reason','?') AS reason,
  count(*)
FROM events
WHERE created_at > now() - interval '20 minutes'
  AND event_type IN ('red_light_violation','speeding')
GROUP BY 1,2,3 ORDER BY 4 DESC;
" 2>&1 || docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT column_name FROM information_schema.columns WHERE table_name='events' ORDER BY 1;
"

echo "=== ALERTS ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT count(*) AS alerts_20m FROM alerts WHERE created_at > now() - interval '20 minutes';
"
