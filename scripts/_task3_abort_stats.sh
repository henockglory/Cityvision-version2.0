#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2
cp /mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/evidence/abort_stats.py \
  ai-engine/src/citevision_ai/evidence/abort_stats.py
cp /mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py \
  ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py
mkdir -p ai-engine/tests
cp /mnt/c/Users/gheno/citevision/ai-engine/tests/test_abort_stats_reconcile.py \
  ai-engine/tests/test_abort_stats_reconcile.py
sed -i 's/\r$//' ai-engine/src/citevision_ai/evidence/abort_stats.py \
  ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py \
  ai-engine/tests/test_abort_stats_reconcile.py

echo "=== unit test 50 attempts ==="
cd ai-engine
.venv/bin/python -m pytest tests/test_abort_stats_reconcile.py -q
cd ..

echo "=== restart AI to load counters ==="
python3 scripts/_restart_ai.py 2>&1 | tail -20

echo "=== abort-stats schema ==="
curl -sf http://127.0.0.1:8001/evidence/abort-stats | python3 -m json.tool | head -40
