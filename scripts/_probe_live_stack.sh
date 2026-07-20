#!/usr/bin/env bash
set -euo pipefail
echo "=== go2rtc streams ==="
curl -sS http://127.0.0.1:1984/api/streams | python3 -c 'import json,sys; d=json.load(sys.stdin); print(list(d.keys()) if isinstance(d,dict) else d)'
echo "=== AI cameras ==="
curl -sS http://127.0.0.1:8001/cameras | python3 -m json.tool | head -100
echo "=== Frigate cameras ==="
curl -sS http://127.0.0.1:5000/api/config | python3 -c 'import json,sys; d=json.load(sys.stdin); print(list((d.get("cameras") or {}).keys()))'
echo "=== recent AI errors ==="
grep -E 'rtsp|404|DESCRIBE|FileVideo|video_file|ERROR|start' /home/gheno/citevision-v2/logs/ai-engine.log | tail -40
