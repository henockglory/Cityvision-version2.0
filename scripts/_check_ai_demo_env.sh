#!/usr/bin/env bash
# Check demo_mode on running AI
curl -sf http://127.0.0.1:8001/health >/dev/null || exit 1
python3 - <<'PY'
import os,sys
sys.path.insert(0,"/home/gheno/citevision-v2/ai-engine/src")
# read from process environ
import subprocess
out=subprocess.check_output(["bash","-lc","tr '\\0' '\\n' < /proc/$(pgrep -f 'uvicorn citevision_ai.main' | head -1)/environ | grep -E 'DEMO|OCR_URL|FRIGATE_'"]).decode()
print(out)
PY
