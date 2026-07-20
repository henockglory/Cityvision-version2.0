#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"

echo "=== AI cameras / frames ==="
curl -sf http://127.0.0.1:8001/cameras | python3 -c '
import json,sys
d=json.load(sys.stdin)
for c in d.get("cameras") or []:
  print(c.get("camera_id"), "run", c.get("running"), "fp", c.get("frames_processed"), "fr", c.get("frames_read"), "err", c.get("last_error"))
'

echo "=== recent DB events (any) last 10 min ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT e.event_type, left(e.camera_id::text,8) cam, e.created_at, left(c.name,30) camname
FROM events e
LEFT JOIN cameras c ON c.id=e.camera_id
WHERE e.created_at > now() - interval '15 minutes'
ORDER BY e.created_at DESC LIMIT 20;
"

echo "=== demo rules enabled? ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT name, is_enabled, left(camera_id::text,8) cam
FROM rules WHERE name LIKE 'Démo%' ORDER BY name;
"

echo "=== red frigate events again ==="
curl -sf 'http://127.0.0.1:5000/api/events?cameras=cv_8ed20433-57d5-4999-a6ab-0bea028b23a3&limit=5' | wc -c
curl -sf 'http://127.0.0.1:5000/api/events?limit=10' | python3 -c '
import json,sys,time
ev=json.load(sys.stdin); now=time.time()
from collections import Counter
print("n",len(ev), "by_cam", Counter(e.get("camera") for e in ev))
for e in ev[:8]:
  print(f"{now-float(e[\"start_time\"]):5.0f}s {e.get(\"camera\",\"\")[:36]} {e.get(\"label\")} zones={e.get(\"zones\")}")
'
