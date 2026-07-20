#!/usr/bin/env bash
set -euo pipefail
cd /home/gheno/citevision-v2/ai-engine
PY=/home/gheno/citevision-v2/ai-engine/.venv/bin/python
export PATH="/usr/local/go/bin:$HOME/go/bin:$PATH"

"$PY" - <<'PY'
from citevision_ai.ingest.segment_cycle_worker import SegmentCycleWorker
try:
    SegmentCycleWorker("x", "rtsp", lambda *a, **k: None)
except RuntimeError as e:
    print("STUB_OK", str(e)[:80])
else:
    raise SystemExit("STUB_FAIL: expected RuntimeError")
PY

"$PY" -m pytest \
  tests/test_evidence_abort_stats.py \
  tests/test_segment_mode.py \
  tests/test_health_gpu_strict.py \
  tests/test_frigate_track_binder.py \
  -q --tb=line

cd /home/gheno/citevision-v2/backend
go test ./internal/evidence/ -count=1
