#!/usr/bin/env bash
set -euo pipefail
SRC=/mnt/c/Users/gheno/citevision/ai-engine
DST=/home/gheno/citevision-v2/ai-engine
FILES=(
  src/citevision_ai/config.py
  src/citevision_ai/pipeline.py
  src/citevision_ai/main.py
  src/citevision_ai/evidence/service.py
  src/citevision_ai/ingest/timeline.py
  src/citevision_ai/ingest/segment_cycle_worker.py
  src/citevision_ai/ingest/rtsp_worker.py
  src/citevision_ai/ingest/file_video_worker.py
  tests/test_segment_mode.py
)
for f in "${FILES[@]}"; do
  cp "$SRC/$f" "$DST/$f"
  sed -i 's/\r$//' "$DST/$f"
done
cp /mnt/c/Users/gheno/citevision/scripts/validate_segment_mode_108.py /home/gheno/citevision-v2/scripts/
sed -i 's/\r$//' /home/gheno/citevision-v2/scripts/validate_segment_mode_108.py
cd "$DST"
.venv/bin/python3 -m pytest tests/test_segment_mode.py tests/test_evidence_capture.py tests/test_evidence_buffer.py -q
