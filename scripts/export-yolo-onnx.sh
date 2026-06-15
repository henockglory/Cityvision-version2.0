#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="$ROOT/ai-engine/models"
VENV="$ROOT/ai-engine/.venv"
DEVICE="${1:-cuda}"

mkdir -p "$MODEL_DIR"
cd "$MODEL_DIR"

if [[ -f yolov8n.onnx && -s yolov8n.onnx && "${FORCE_EXPORT:-0}" != "1" ]]; then
  echo "[OK] yolov8n.onnx exists ($(du -h yolov8n.onnx | cut -f1))"
  exit 0
fi

if [[ ! -f yolov8n.pt ]]; then
  curl -fSL -o yolov8n.pt "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.pt"
fi

python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip

if [[ "$DEVICE" == "cuda" ]] && command -v nvidia-smi >/dev/null 2>&1; then
  echo "[INFO] Export with PyTorch CUDA"
  "$VENV/bin/pip" install -q torch torchvision --index-url https://download.pytorch.org/whl/cu124 || \
    "$VENV/bin/pip" install -q torch torchvision
else
  echo "[INFO] Export with PyTorch CPU (no nvidia-smi)"
  "$VENV/bin/pip" install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu
fi
"$VENV/bin/pip" install -q ultralytics onnx onnxruntime onnxsim

"$VENV/bin/python" - <<'PY'
from ultralytics import YOLO
YOLO("yolov8n.pt").export(format="onnx", imgsz=640, opset=12, simplify=True)
print("[OK] Exported yolov8n.onnx")
PY

ls -lah yolov8n.onnx
