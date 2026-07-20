#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
EID=$(curl -sf 'http://127.0.0.1:5000/api/events?cameras=cv_55694d53-8f58-4981-91b2-7c6cd528a25d&limit=1' | python3 -c 'import sys,json;print(json.load(sys.stdin)[0]["id"])')
echo "EID=$EID"
echo "=== clip body ==="
curl -sS --max-time 10 "http://127.0.0.1:5000/api/events/$EID/clip.mp4" | head -c 200; echo
echo "=== camera yaml snippet ==="
python3 - <<'PY'
from pathlib import Path
text=Path("/home/gheno/citevision-v2/infra/frigate-config/config.yml").read_text()
cam="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
i=text.find(cam+":")
print(text[i:i+900])
print("--- global record ---")
# find top-level record before cameras
idx=text.find("\ncameras:")
print(text[:idx][-800:] if idx>0 else text[:800])
PY
echo "=== frigate recordings ==="
curl -sf --max-time 5 'http://127.0.0.1:5000/api/recordings/summary' | head -c 400; echo
echo "=== docker logs frigate ==="
docker logs --tail 40 citevision-v2-frigate 2>&1 | tail -40
echo "=== disk media ==="
docker exec citevision-v2-frigate sh -c 'df -h /media/frigate; ls -la /media/frigate 2>/dev/null | head; find /media/frigate -name "*.mp4" 2>/dev/null | head'
