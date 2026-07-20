#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT payload FROM events e JOIN cameras c ON c.id=e.camera_id WHERE e.event_type='speeding' AND e.ingested_at>now()-interval '10 minutes' ORDER BY e.ingested_at DESC LIMIT 1;" \
  > /tmp/speed_evt.json

python3 - <<'PY'
import json, urllib.request
from pathlib import Path
raw=Path("/tmp/speed_evt.json").read_text().strip()
print("payload_len", len(raw))
evt=json.loads(raw)
# freshen timestamps toward now so Frigate align works
import time
now=time.time()
evt["bbox_ts"]=now
evt["timestamp"]=time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now))
body={"org_id":"74d51ead-97a7-4e41-a488-503a9b90c466","event":evt,"evidence":{}}
cam="55694d53-8f58-4981-91b2-7c6cd528a25d"
print("posting capture event_type", evt.get("event_type"), "track", evt.get("track_id"))
req=urllib.request.Request(
    f"http://127.0.0.1:8001/cameras/{cam}/evidence/capture",
    data=json.dumps(body).encode(),
    headers={"Content-Type":"application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=240) as r:
        data=json.loads(r.read())
        print("OK status", r.status)
        pkg=data.get("package") or (data.get("evidence") or {}).get("package") or {}
        meta=(pkg.get("metadata") or {}) if isinstance(pkg, dict) else {}
        print("evidence_status", data.get("evidence_status"), meta.get("capture_source"), meta.get("frigate_event_id"))
        print("keys", list(data.keys())[:20])
except Exception as e:
    print("ERR", e)
    if hasattr(e, "read"):
        print(e.read()[:800])
PY

echo "=== AI log snippet ==="
grep -E 'dedupe|frigate_track|ERROR|Exception|WARN.*evidence|WARN.*frigate' "$ROOT/logs/ai-engine.log" | tail -50
