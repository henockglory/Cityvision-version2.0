#!/usr/bin/env bash
set -euo pipefail
WIN=/mnt/c/Users/gheno/citevision
WSL=/home/gheno/citevision-v2

mkdir -p "$WSL/_archive/segment_mode" "$WSL/ops/diagnostics"
rsync -a --delete "$WIN/_archive/segment_mode/" "$WSL/_archive/segment_mode/"
rsync -a --delete "$WIN/ops/diagnostics/" "$WSL/ops/diagnostics/"

FILES=(
  ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py
  ai-engine/src/citevision_ai/ingest/segment_cycle_worker.py
  ai-engine/src/citevision_ai/ingest/rtsp_worker.py
  ai-engine/src/citevision_ai/config.py
  backend/internal/evidence/completeness.go
  backend/internal/evidence/completeness_test.go
  .cursor/rules/citevision-socle.mdc
)

for f in "${FILES[@]}"; do
  mkdir -p "$(dirname "$WSL/$f")"
  cp -f "$WIN/$f" "$WSL/$f"
  sed -i 's/\r$//' "$WSL/$f"
done

find "$WSL/scripts" -maxdepth 1 \( -name '_fix_*' -o -name '_diag_*' \) -type f -delete 2>/dev/null || true

echo SYNC_OK
ls "$WSL/_archive/segment_mode/"
echo "diagnostics_count=$(ls "$WSL/ops/diagnostics" | wc -l)"
head -3 "$WSL/ai-engine/src/citevision_ai/ingest/segment_cycle_worker.py"
grep -n 'plate_jpeg = subject' "$WSL/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py" || echo NO_PLATE_FALLBACK
grep -n 'role != "plate"' "$WSL/backend/internal/evidence/completeness.go" || echo PLATE_REQUIRED_OK
# truncation checks
grep -n 'FrameRingBuffe[^r]' "$WSL/ai-engine/src/citevision_ai/evidence/service.py" || echo NO_TRUNC_BUFFER
grep -n 'urllib\.erro$' "$WSL/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py" || echo NO_URLLIB_TRUNC
