#!/usr/bin/env bash
set -euo pipefail
WIN=/mnt/c/Users/gheno/citevision
DEST=~/citevision-v2
files=(
  ai-engine/src/citevision_ai/evidence/capture.py
  ai-engine/src/citevision_ai/evidence/service.py
  ai-engine/src/citevision_ai/pipeline.py
  ai-engine/src/citevision_ai/analytics/zone_speed.py
  ai-engine/tests/test_emission_track_bbox.py
  ai-engine/tests/test_live_evidence_alignment.py
  ai-engine/tests/test_speed_evidence_e2e.py
)
for f in "${files[@]}"; do
  sed 's/\r$//' "$WIN/$f" > "$DEST/$f"
  echo "synced $f"
done
