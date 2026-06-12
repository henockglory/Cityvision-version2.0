#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="$ROOT/ai-engine/models"
MODEL_PATH="$MODEL_DIR/yolov8n.onnx"

mkdir -p "$MODEL_DIR"

if [ -f "$MODEL_PATH" ]; then
  echo "Model already exists: $MODEL_PATH"
  exit 0
fi

echo "==> Downloading YOLOv8n ONNX model"

# Primary: Ultralytics export URL (community mirror)
URL="https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.onnx"

if curl -fsSL -o "$MODEL_PATH" "$URL"; then
  echo "Downloaded to $MODEL_PATH"
  exit 0
fi

echo "Direct download failed. Creating minimal placeholder ONNX for CI/dev."
python3 - <<'PY'
import struct
import sys
from pathlib import Path

path = Path(sys.argv[1])
# Minimal valid ONNX protobuf header placeholder (tests use mock inference)
path.write_bytes(b"\x08\x07" + b"\x00" * 64)
print(f"Placeholder written: {path}")
PY
"$MODEL_PATH"

echo "Run ultralytics export manually for production:"
echo "  yolo export model=yolov8n.pt format=onnx"
