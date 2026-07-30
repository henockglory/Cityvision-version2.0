#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cd "$ROOT"

if git rev-parse --git-dir >/dev/null 2>&1; then
  git fetch v2 2>/dev/null || git fetch origin 2>/dev/null || true
  git reset --hard 08129643a227191b9f812cb7d1f59209737db8c3
  echo "WSL git HEAD=$(git rev-parse --short HEAD) $(git log -1 --oneline)"
else
  echo "WSL not a git repo — rsync only"
fi

rsync -a --delete --checksum \
  "$WIN/ai-engine/src/citevision_ai/" \
  "$ROOT/ai-engine/src/citevision_ai/"

if [[ -f "$WIN/rules-engine/internal/actions/executor.go" ]]; then
  mkdir -p "$ROOT/rules-engine/internal/actions"
  rsync -a --checksum \
    "$WIN/rules-engine/internal/actions/executor.go" \
    "$ROOT/rules-engine/internal/actions/executor.go"
fi

echo "=== WIP markers (should be empty/minimal for 0812964) ==="
grep -n "_road_end_lag_sec\|_demo_zone_vehicle\|_trim_clip_bytes_around\|subject_binding_zone" \
  "$ROOT/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py" | head -20 || echo "(none)"

bash "$ROOT/scripts/_quick_restart_ai.sh"
sleep 8
curl -sf http://127.0.0.1:8001/health | head -c 160 || echo "AI health fail"
echo
