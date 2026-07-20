#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2

# Restart Vite if down
if ! curl -sf --max-time 2 http://127.0.0.1:5174/ >/dev/null; then
  cd "$ROOT/frontend"
  nohup npm run dev -- --host 127.0.0.1 --port 5174 > /tmp/citevision-vite.log 2>&1 &
  sleep 3
fi

echo "=== AI cam ==="
curl -sS http://127.0.0.1:8001/cameras | python3 -c '
import json,sys
for c in json.load(sys.stdin).get("cameras") or []:
  print(c.get("camera_id")[:8], "fr", c.get("frames_read"), "fp", c.get("frames_processed"), "err", c.get("last_error"))
'

echo "=== rules-engine suppress (tail) ==="
grep -E 'suppressed|incomplete|502|ensureEvidence|9e66ecfa|speeding' "$ROOT/logs/rules-engine.log" | tail -25

echo "=== AI evidence (tail) ==="
grep -aE 'frigate_track:|abort|semaphore|55694d53|capture unavailable|missing_roles|plate' "$ROOT/logs/ai-engine.log" | tail -30

echo "=== abort stats ==="
curl -sf http://127.0.0.1:8001/evidence/abort-stats 2>/dev/null | python3 -m json.tool 2>/dev/null | head -40 || echo no_endpoint
