#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2

for f in \
  ai-engine/src/citevision_ai/config.py \
  ai-engine/src/citevision_ai/evidence/service.py \
  ai-engine/tests/test_demo_loop_meta.py \
  frontend/src/components/evidence/EvidenceViewer.tsx
do
  mkdir -p "$(dirname "$f")"
  cp "/mnt/c/Users/gheno/citevision/$f" "$f"
  sed -i 's/\r$//' "$f"
  echo "ok $f"
done

echo "=== unit test loop meta ==="
cd ai-engine && .venv/bin/python -m pytest tests/test_demo_loop_meta.py -q && cd ..

echo "=== restart AI ==="
python3 scripts/_restart_ai.py 2>&1 | tail -25

echo "=== smoke: allows ring for red_light ==="
ai-engine/.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, "ai-engine/src")
from citevision_ai.evidence.service import EvidenceCaptureService
from citevision_ai.config import settings
print("demo_mode", settings.demo_mode, settings.demo_mode_source)
print("demo_relaxed", settings.demo_relaxed_evidence())
svc = EvidenceCaptureService()
print("backend_mode", svc._evidence_backend_mode())
print("allows_red", svc._allows_ring_buffer_fallback({"event_type": "red_light_violation"}))
print("loop", svc._demo_loop_meta("cam", 100.0))
PY
