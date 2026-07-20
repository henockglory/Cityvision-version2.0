#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
echo "=== AI cam ==="
curl -sS http://127.0.0.1:8001/cameras | python3 -c '
import json,sys
for c in json.load(sys.stdin).get("cameras") or []:
  print(c.get("camera_id")[:8], "fr", c.get("frames_read"), "fp", c.get("frames_processed"), "err", c.get("last_error"))
'
echo "=== rules enabled ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
"SELECT name||'|'||is_enabled FROM rules WHERE org_id='74d51ead-97a7-4e41-a488-503a9b90c466'::uuid AND name LIKE 'Démo%' ORDER BY name;"
echo "=== rules-engine ==="
curl -sf http://127.0.0.1:8010/health; echo
echo "=== suppress/phone tail ==="
grep -E 'phone|suppressed|incomplete|502|ensureEvidence|4ffec4e0|Téléphone' "$ROOT/logs/rules-engine.log" | tail -30
echo "=== AI evidence cabin ==="
grep -aE 'f691ef55|phone_use|semaphore|cabin|capture_source' "$ROOT/logs/ai-engine.log" | tail -25
echo "=== recent phone events ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
"SELECT e.event_type, e.ingested_at FROM events e JOIN cameras c ON c.id=e.camera_id
 WHERE c.org_id='74d51ead-97a7-4e41-a488-503a9b90c466'::uuid
   AND e.event_type LIKE '%phone%' AND e.ingested_at > now() - interval '20 minutes'
 ORDER BY e.ingested_at DESC LIMIT 8;"
