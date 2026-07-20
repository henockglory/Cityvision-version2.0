#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2

echo "=== AI cameras ==="
curl -sS http://127.0.0.1:8001/cameras | python3 -c '
import json,sys
for c in json.load(sys.stdin).get("cameras") or []:
  print(c.get("camera_id"), "fr", c.get("frames_read"), "fp", c.get("frames_processed"), "url", c.get("rtsp_url"), "err", c.get("last_error"))
'

echo "=== evidence backend / env ==="
grep -E 'EVIDENCE_BACKEND|FRIGATE_|OCR_' /home/gheno/citevision-v2/.env | head -30

echo "=== phone alert snapshot roles ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c "
SELECT left(a.evidence_snapshot::text, 1200)
FROM alerts a WHERE a.id='853edad7'::uuid OR a.id::text LIKE '853edad7%'
ORDER BY a.created_at DESC LIMIT 1;" 2>/dev/null | head -c 1500
echo

docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -F'|' -c "
SELECT a.id::text,
  a.evidence_snapshot->'package'->'metadata'->>'capture_source',
  a.evidence_snapshot->'package'->>'evidence_status',
  (SELECT string_agg(im->>'role', ',') FROM jsonb_array_elements(COALESCE(a.evidence_snapshot->'package'->'images','[]'::jsonb)) im),
  a.evidence_snapshot->'package'->'clip'->>'asset_id' IS NOT NULL
FROM alerts a
WHERE a.created_at > now() - interval '2 hours'
ORDER BY a.created_at DESC LIMIT 8;"

echo "=== AI frigate_track recent ==="
grep -aE 'frigate_track:|capture_source|IoU|missing|abort|f691ef55|8ed20433|55694d53' "$ROOT/logs/ai-engine.log" | tail -50
