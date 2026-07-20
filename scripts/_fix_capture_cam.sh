#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
source "$ROOT/scripts/lib/env-utils.sh"
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

echo "=== AI cameras ==="
curl -sS http://127.0.0.1:8001/cameras | python3 -m json.tool | head -80

echo "=== force resync ==="
curl -sf -X POST http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial -H "X-Internal-Key: $KEY"; echo
sleep 8
curl -sS http://127.0.0.1:8001/cameras | python3 -c '
import json,sys
for c in json.load(sys.stdin).get("cameras") or []:
  print(c.get("camera_id"), "run", c.get("running"), "fr", c.get("frames_read"), "fp", c.get("frames_processed"), "err", c.get("last_error"))
'

echo "=== try capture on speed cam ==="
CAM=55694d53-8f58-4981-91b2-7c6cd528a25d
curl -sS -X POST "http://127.0.0.1:8001/cameras/$CAM/evidence/capture" \
  -H 'Content-Type: application/json' \
  -d '{"event_type":"speeding","anchor_ts":null}' | head -c 800; echo

echo "=== AI evidence log ==="
grep -E 'capture unavailable|frigate_track|evidence|ERROR' "$ROOT/logs/ai-engine.log" | tail -40
