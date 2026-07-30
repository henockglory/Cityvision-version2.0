#!/usr/bin/env bash
set -euo pipefail
WIN=/mnt/c/Users/gheno/citevision
WSL=/home/gheno/citevision-v2
rsync -a --checksum \
  "$WIN/ai-engine/src/citevision_ai/config.py" \
  "$WSL/ai-engine/src/citevision_ai/config.py"
rsync -a --checksum \
  "$WIN/ai-engine/src/citevision_ai/evidence/service.py" \
  "$WIN/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py" \
  "$WSL/ai-engine/src/citevision_ai/evidence/"
rsync -a --checksum \
  "$WIN/ai-engine/tests/test_zone_binding_evidence.py" \
  "$WSL/ai-engine/tests/test_zone_binding_evidence.py"
cd "$WSL/ai-engine"
. .venv/bin/activate
python -m pytest tests/test_zone_binding_evidence.py tests/test_frigate_track_binder.py tests/test_frigate_bound_capture.py -q --tb=line
bash "$WSL/scripts/_quick_restart_ai.sh"
sleep 6
curl -sf http://127.0.0.1:8001/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('health', d.get('status'), 'demo', d.get('demo_mode'))"
