#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
grep -n 'dedupe skip (retro)\|_begin_speed_evidence' \
  "$ROOT/ai-engine/src/citevision_ai/evidence/service.py" | head -20
echo "404s=$(grep -c '404 Not Found' $ROOT/logs/ai-engine.log || true)"
echo "dedupe=$(grep -c 'dedupe skip' $ROOT/logs/ai-engine.log || true)"
echo "frigate=$(grep -c 'frigate_track' $ROOT/logs/ai-engine.log || true)"

docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT payload FROM events e JOIN cameras c ON c.id=e.camera_id WHERE e.event_type='speeding' AND e.ingested_at>now()-interval '5 minutes' ORDER BY e.ingested_at DESC LIMIT 1;" \
  > /tmp/speed_evt.json

python3 - <<'PY'
import json
from pathlib import Path
raw=Path("/tmp/speed_evt.json").read_text().strip()
print("len", len(raw))
if not raw:
    raise SystemExit(0)
d=json.loads(raw)
print("keys", sorted(d.keys()))
print("event_type=", d.get("event_type"), "event=", d.get("event"))
print("track_id=", d.get("track_id"), "evidence_status=", d.get("evidence_status"))
print("has package", "package" in d, "evidence" in d)
# show bbox_ts / timestamp fields
for k in ("bbox_ts","timestamp","event_ts","ts","detected_at"):
    if k in d: print(k, d[k])
PY

# Manual retro capture once with logging
python3 - <<'PY'
import json, urllib.request, time
from pathlib import Path
raw=Path("/tmp/speed_evt.json").read_text().strip()
if not raw:
    print("no event"); raise SystemExit(0)
evt=json.loads(raw)
body={"org_id":"74d51ead-97a7-4e41-a488-503a9b90c466","event":evt,"evidence":None}
cam="55694d53-8f58-4981-91b2-7c6cd528a25d"
req=urllib.request.Request(
    f"http://127.0.0.1:8001/cameras/{cam}/evidence/capture",
    data=json.dumps(body).encode(),
    headers={"Content-Type":"application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=180) as r:
        print("status", r.status)
        print(r.read()[:500])
except Exception as e:
    print("ERR", type(e), e)
    if hasattr(e, 'read'):
        print(e.read())
PY

echo "=== log after manual ==="
grep -E 'dedupe|frigate_track|ERROR|Exception|Traceback' "$ROOT/logs/ai-engine.log" | tail -40
