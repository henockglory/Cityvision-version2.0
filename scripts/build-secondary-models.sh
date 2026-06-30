#!/usr/bin/env bash
# Build or download secondary ONNX models (phone cls + seatbelt det).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VENV="${ROOT}/ai-engine/.venv/bin/python"
[[ -x "$VENV" ]] || VENV="$(command -v python3)"

echo "=== build-secondary-models ==="
"$VENV" -m pip install -q ultralytics onnx onnxruntime 2>/dev/null || \
  "$VENV" -m pip install -q ultralytics onnx onnxruntime

export SEATBELT_PT_URL="${SEATBELT_PT_URL:-https://github.com/KorkanaRahul/Seatbelt-Detection-Using-DWYOLOv8-Model/raw/main/Weights/seatbeltWbest%20(1).pt}"
export SEATBELT_EPOCHS="${SEATBELT_EPOCHS:-20}"

"$VENV" "$ROOT/ai-engine/scripts/build_secondary_models.py" "$@"
bash "$ROOT/scripts/download-secondary-models.sh" --fix 2>/dev/null || true

echo "=== Health check (secondary models) ==="
curl -sf "http://localhost:${AI_ENGINE_PORT:-8001}/health" 2>/dev/null | "$VENV" -c "
import json, sys
try:
    d = json.load(sys.stdin)
    for k in ('driver_phone_model_loaded', 'seatbelt_model_loaded'):
        print(f'{k}: {d.get(k)}')
except Exception:
    print('AI engine not running — restart after build')
" || true
