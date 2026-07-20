#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
SRC=/mnt/c/Users/gheno/citevision
files=(
  ai-engine/src/citevision_ai/evidence/frigate_timeline.py
  ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py
  ai-engine/src/citevision_ai/config.py
  ai-engine/tests/test_demo_loop_guard.py
  ai-engine/tests/test_frigate_timeline.py
  ai-engine/tests/test_frigate_backend.py
  ai-engine/tests/test_frigate_correlation_accept_gate.py
)
for f in "${files[@]}"; do
  cp "$SRC/$f" "$ROOT/$f"
  sed -i 's/\r$//' "$ROOT/$f"
  echo "synced $f"
done
cd "$ROOT/ai-engine"
.venv/bin/python -m pytest \
  tests/test_demo_loop_guard.py \
  tests/test_frigate_timeline.py \
  tests/test_frigate_correlation_accept_gate.py \
  tests/test_frigate_backend.py::FrigateTrackEvidenceTests::test_accept_correlation_rejects_high_align_delta \
  tests/test_frigate_backend.py::FrigateTrackEvidenceTests::test_accept_correlation_rejects_low_iou \
  tests/test_frigate_backend.py::FrigateTrackEvidenceTests::test_accept_correlation_accepts_tight_match \
  -q --tb=short
