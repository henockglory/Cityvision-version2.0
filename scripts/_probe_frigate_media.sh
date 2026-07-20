#!/usr/bin/env bash
set -uo pipefail
# Inspect why compose returns None for a known Frigate event
EID=$(curl -sf 'http://127.0.0.1:5000/api/events?cameras=cv_55694d53-8f58-4981-91b2-7c6cd528a25d&limit=1' | python3 -c 'import sys,json; e=json.load(sys.stdin); print(e[0]["id"] if e else "")')
echo "EID=$EID"
curl -sf "http://127.0.0.1:5000/api/events/$EID" | python3 -c 'import sys,json; d=json.load(sys.stdin); print({k:d.get(k) for k in ("id","label","has_clip","has_snapshot","start_time","end_time")}); print("box",(d.get("data") or {}).get("box"))'

echo "=== clip HTTP ==="
code=$(curl -sS -o /tmp/fclip.mp4 -w '%{http_code}' --max-time 60 "http://127.0.0.1:5000/api/events/$EID/clip.mp4" || echo err)
echo "clip_http=$code size=$(wc -c </tmp/fclip.mp4 2>/dev/null || echo 0)"

echo "=== snapshot HTTP ==="
code=$(curl -sS -o /tmp/fsnap.jpg -w '%{http_code}' --max-time 30 "http://127.0.0.1:5000/api/events/$EID/snapshot.jpg" || echo err)
echo "snap_http=$code size=$(wc -c </tmp/fsnap.jpg 2>/dev/null || echo 0)"

echo "=== thumbnail ==="
code=$(curl -sS -o /tmp/fthumb.jpg -w '%{http_code}' --max-time 30 "http://127.0.0.1:5000/api/events/$EID/thumbnail.jpg" || echo err)
echo "thumb_http=$code size=$(wc -c </tmp/fthumb.jpg 2>/dev/null || echo 0)"

# config snapshots for speed cam
python3 - <<'PY'
from pathlib import Path
import re
text=Path("/home/gheno/citevision-v2/infra/frigate-config/config.yml").read_text()
cam="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
for key in ("record","snapshots"):
  m=re.search(rf"{re.escape(cam)}:.*?{key}:\s*\n\s*enabled:\s*(true|false)", text, re.S)
  print(key, m.group(1) if m else "?")
PY
