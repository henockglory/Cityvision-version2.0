#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
echo "=== AI traffic_light / red_light ==="
grep -E 'traffic_light|red_light_violation|abort red_light|ignore stale' "$ROOT/logs/ai-engine.log" | tail -40 || true
echo "counts violation=$(grep -c red_light_violation "$ROOT/logs/ai-engine.log" 2>/dev/null || echo 0) abort=$(grep -c 'abort red_light' "$ROOT/logs/ai-engine.log" 2>/dev/null || echo 0)"
echo "=== UI ==="
curl -sf --max-time 3 -o /dev/null -w "UI %{http_code}\n" http://127.0.0.1:5174/ || echo UI_DOWN
echo "=== recent events DB ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c "
SELECT column_name FROM information_schema.columns WHERE table_name='events' ORDER BY ordinal_position LIMIT 30;
"
