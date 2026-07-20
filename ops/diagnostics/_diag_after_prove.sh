#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
echo "=== frigate ==="
curl -sf --max-time 3 http://127.0.0.1:5000/api/version || echo DOWN
docker ps --format '{{.Names}} {{.Status}}' | grep -E 'frigate|go2rtc' || true
echo "=== AI log evidence ==="
wc -c "$ROOT/logs/ai-engine.log"
grep -E 'dedupe|frigate_track|retroactive|semaphore|ERROR|Exception|Traceback|evidence' "$ROOT/logs/ai-engine.log" | tail -60
echo "=== stats ==="
curl -sf --max-time 5 http://127.0.0.1:5000/api/stats 2>/dev/null | python3 -c 'import sys,json;d=json.load(sys.stdin);c=(d.get("cameras")or{}).get("cv_55694d53-8f58-4981-91b2-7c6cd528a25d")or{};print("fps",c.get("camera_fps"),"det",c.get("detection_fps"))' || echo no_stats
