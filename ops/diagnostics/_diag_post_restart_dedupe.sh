#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
echo "=== log lines after AI start (16:07) ==="
# AI pid started ~16:07 local
awk '/2026-07-16 16:0[7-9]|2026-07-16 16:[1-9]/ {
  if ($0 ~ /speed evidence dedupe/) d++
  if ($0 ~ /semaphore timeout/) s++
  if ($0 ~ /frigate_track:/) f++
  if ($0 ~ /frigate_track: bound|demo vehicle|compose|upload/) ok++
}
END { print "dedupe",d+0,"sem",s+0,"frigate_lines",f+0,"okish",ok+0 }
' "$ROOT/logs/ai-engine.log"

echo "=== recent frigate_track after 16:07 ==="
grep -E '2026-07-16 16:(0[7-9]|[1-5][0-9]).*frigate_track' "$ROOT/logs/ai-engine.log" | tail -30

echo "=== segment mode cams ==="
grep -E 'SEGMENT_MODE|parsed_segment' "$ROOT/.env" || true
grep -n 'segment_mode' "$ROOT/ai-engine/src/citevision_ai/config.py" | head -10

echo "=== AI cameras ==="
curl -sf http://127.0.0.1:8001/cameras | python3 -c 'import sys,json; d=json.load(sys.stdin); cams=d.get("cameras",d if isinstance(d,list) else []);
print("n", len(cams) if isinstance(cams,list) else cams);
[print(c.get("camera_id","?")[:8], "proc", c.get("frames_processed"), "err", c.get("last_error")) for c in (cams if isinstance(cams,list) else [])][:10]'

echo "=== validation still running? ==="
pgrep -af '_validate_rule_frigate' || echo none
