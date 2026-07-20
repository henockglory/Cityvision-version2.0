#!/usr/bin/env bash
set -uo pipefail
ORG=74d51ead-97a7-4e41-a488-503a9b90c466

echo "=== demo settings ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
"SELECT source_mode, active_video_id, active_camera_id FROM org_demo_settings WHERE org_id='$ORG'::uuid;"

echo "=== Frigate stats ==="
curl -sS http://127.0.0.1:5000/api/stats | python3 -c '
import json,sys,time
d=json.load(sys.stdin)
for k,v in (d.get("cameras") or {}).items():
  print(k[:40], "fps", v.get("camera_fps"), "det", v.get("detection_fps"), "pid", v.get("pid"))
'

echo "=== Frigate latest events ==="
curl -sS "http://127.0.0.1:5000/api/events?limit=8" | python3 -c '
import json,sys,time
now=time.time()
for e in json.load(sys.stdin)[:8]:
  st=float(e.get("start_time") or 0)
  print(f"age={now-st:.0f}s cam={e.get(\"camera\",\"\")[:28]} label={e.get(\"label\")} id={str(e.get(\"id\",\"\"))[:22]}")
'

echo "=== artefacts ==="
find /home/gheno/citevision-v2/validation-evidence -name report.json 2>/dev/null | sort | while read f; do
  python3 -c "import json;d=json.load(open('$f'));print('$f', 'result='+str(d.get('result')), 'alias='+str(d.get('alias','')))"
done

echo "=== validate log tail ==="
tail -40 /home/gheno/citevision-v2/logs/validate-all-5.log
