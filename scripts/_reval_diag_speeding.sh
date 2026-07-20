#!/usr/bin/env bash
set -uo pipefail
echo "=== rules-engine suppress/capture (tail) ==="
grep -aE 'incomplete evidence|capture unavailable|alert suppressed|evidence/request|speeding' \
  /home/gheno/citevision-v2/logs/rules-engine.log 2>/dev/null | tail -40
echo "=== AI evidence (tail) ==="
grep -aE 'speeding|capture unavailable|demo_ring|frigate|abort|incomplete' \
  /home/gheno/citevision-v2/logs/ai-engine.log 2>/dev/null | tail -40
echo "=== abort-stats ==="
curl -sf http://127.0.0.1:8001/evidence/abort-stats | python3 -m json.tool 2>/dev/null | head -50
echo "=== DB events/alerts last 30m ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT 'events' t, count(*) FROM events WHERE created_at > now()-interval '30 minutes'
   UNION ALL SELECT 'alerts', count(*) FROM alerts WHERE created_at > now()-interval '30 minutes';"
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT event_type, count(*) FROM events WHERE created_at > now()-interval '30 minutes' GROUP BY 1;"
echo "=== demo rules ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT name, is_enabled FROM rules WHERE name LIKE 'Démo%' ORDER BY name;"
# always OFF + purge even after fail
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "UPDATE rules SET is_enabled=false WHERE name LIKE 'Démo%';" >/dev/null
cd /home/gheno/citevision-v2
FRIGATE_DEMO_RETENTION_MIN=30 bash scripts/demo-retention-purge.sh || true
sudo fstrim -v / || true
