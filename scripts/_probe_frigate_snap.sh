#!/usr/bin/env bash
set -euo pipefail
# Quick probe: snapshot vs thumbnail vs clip for latest event
fc=cv_55694d53-8f58-4981-91b2-7c6cd528a25d
eid=$(python3 - <<PY
import json,urllib.request
ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras=$fc&limit=1",timeout=8).read())
print(ev[0]["id"])
print("has_snap", ev[0].get("has_snapshot"), "has_clip", ev[0].get("has_clip"), file=__import__('sys').stderr)
PY
)
echo "eid=$eid"
for path in "snapshot.jpg?bbox=1" "snapshot.jpg" "thumbnail.jpg" "snapshot-clean.webp"; do
  code=$(curl -s -o /tmp/fr.jpg -w "%{http_code}" "http://127.0.0.1:5000/api/events/$eid/$path" || true)
  sz=$(wc -c </tmp/fr.jpg 2>/dev/null || echo 0)
  echo "  $path -> HTTP $code size=$sz"
done
