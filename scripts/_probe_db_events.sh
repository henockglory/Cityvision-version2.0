#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

echo "=== schema events/rules cols ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "\d events" | head -40
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "\d rules" | head -40

echo "=== recent events ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT event_type, left(camera_id::text,8) cam, occurred_at
FROM events
WHERE occurred_at > now() - interval '20 minutes'
ORDER BY occurred_at DESC LIMIT 25;
" 2>/dev/null || docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT event_type, left(camera_id::text,8) cam, timestamp
FROM events
ORDER BY timestamp DESC LIMIT 25;
"

echo "=== demo rules ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT name, is_enabled FROM rules WHERE name LIKE 'D%' ORDER BY name;
"

echo "=== frigate events by cam ==="
python3 - <<'PY'
import json,urllib.request,time
from collections import Counter
with urllib.request.urlopen('http://127.0.0.1:5000/api/events?limit=30', timeout=10) as r:
    ev=json.loads(r.read().decode())
now=time.time()
print('n',len(ev), 'by', Counter(e.get('camera') for e in ev))
for e in ev[:12]:
    print(f"{now-float(e['start_time']):5.0f}s {str(e.get('camera'))[:40]} {e.get('label')} z={e.get('zones')}")
# red specifically
cam='cv_8ed20433-57d5-4999-a6ab-0bea028b23a3'
with urllib.request.urlopen(f'http://127.0.0.1:5000/api/events?cameras={cam}&limit=10', timeout=10) as r:
    ev2=json.loads(r.read().decode())
print('red_n', len(ev2))
for e in ev2[:5]:
    print(' red', now-float(e['start_time']), e.get('label'), e.get('end_time') is None)
PY
