#!/usr/bin/env bash
set -euo pipefail
SRC=/mnt/c/Users/gheno/citevision/ai-engine
DST=/home/gheno/citevision-v2/ai-engine
for f in \
  src/citevision_ai/evidence/config.py \
  src/citevision_ai/evidence/buffer.py \
  src/citevision_ai/evidence/service.py \
  src/citevision_ai/ingest/rtsp_worker.py \
  src/citevision_ai/ingest/file_video_worker.py \
  src/citevision_ai/main.py \
  tests/test_evidence_buffer.py; do
  cp "$SRC/$f" "$DST/$f"
  sed -i 's/\r$//' "$DST/$f"
done
cd "$DST"
.venv/bin/python3 -m pytest tests/test_evidence_buffer.py tests/test_evidence_capture.py -q
