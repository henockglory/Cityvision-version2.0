#!/usr/bin/env bash
set -uo pipefail
PSQL() { docker exec -i citevision-v2-postgres psql -U citevision -d citevision -tAc "$1"; }
echo "=== demo events by type (last 24h) ==="
PSQL "SELECT event_type, count(*) FROM events WHERE payload->>'demo'='true' AND occurred_at > now() - interval '24 hours' GROUP BY event_type ORDER BY count(*) DESC;"
echo "=== demo alerts (last 24h) ==="
PSQL "SELECT count(*) AS demo_alerts FROM alerts WHERE (metadata->>'demo')='true' AND created_at > now() - interval '24 hours';"
echo "=== demo rules is_enabled ==="
PSQL "SELECT name, is_enabled FROM rules WHERE name LIKE 'Démo%' ORDER BY name;"
echo "=== line counter ==="
PSQL "SELECT line_id, count_total FROM line_counters ORDER BY count_total DESC LIMIT 3;"
echo "=== mailhog total ==="
curl -s http://localhost:8025/api/v2/messages?limit=1 | python3 -c "import sys,json;print('mails_total=',json.load(sys.stdin).get('total'))" 2>/dev/null || echo "mailhog unreachable"
echo "=== AI health ==="
curl -s http://localhost:8001/health
