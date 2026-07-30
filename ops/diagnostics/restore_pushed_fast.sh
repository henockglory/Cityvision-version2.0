#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
echo "rsync ai-engine from Windows 0812964..."
rsync -a --delete --checksum \
  "$WIN/ai-engine/src/citevision_ai/" \
  "$ROOT/ai-engine/src/citevision_ai/"
echo "rsync rules executor..."
mkdir -p "$ROOT/rules-engine/internal/actions"
cp -f "$WIN/rules-engine/internal/actions/executor.go" \
  "$ROOT/rules-engine/internal/actions/executor.go"
echo "check WIP markers:"
grep -c "_road_end_lag_sec\|_trim_clip_bytes_around\|_demo_zone_vehicle" \
  "$ROOT/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py" || echo "0 matches OK"
echo "restart AI..."
bash "$ROOT/scripts/_quick_restart_ai.sh"
sleep 6
curl -sf http://127.0.0.1:8001/health | head -c 140 || echo FAIL
echo
echo "done"
