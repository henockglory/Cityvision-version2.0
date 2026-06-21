#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="$ROOT/ai-engine/models"
# shellcheck source=scripts/lib/wsl-root.sh
source "$ROOT/scripts/lib/wsl-root.sh"
ensure_venv_not_on_drvfs
VENV="$(resolve_venv_dir)"
DEVICE="${1:-cuda}"
ONNX_NAME="${YOLO_MODEL:-yolov8n.onnx}"
PT_NAME="${ONNX_NAME%.onnx}.pt"

mkdir -p "$MODEL_DIR"
cd "$MODEL_DIR"

if [[ -f "$ONNX_NAME" && -s "$ONNX_NAME" && "${FORCE_EXPORT:-0}" != "1" ]]; then
  echo "[OK] $ONNX_NAME exists ($(du -h "$ONNX_NAME" | cut -f1))"
  exit 0
fi

if [[ ! -f "$PT_NAME" ]]; then
  echo "[INFO] Downloading $PT_NAME…"
  curl -fSL -o "$PT_NAME" "https://github.com/ultralytics/assets/releases/download/v8.2.0/${PT_NAME}"
fi

# Never run "python -m venv" on ai-engine/.venv when it is a symlink on drvfs —
# create/use the physical ext4 path from resolve_venv_dir instead.
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "[INFO] Creating export venv at $VENV…"
  python3.12 -m venv "$VENV" 2>/dev/null || python3 -m venv "$VENV"
fi

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

"$VENV/bin/python" - <<PY
from ultralytics import YOLO
YOLO("${PT_NAME}").export(format="onnx", imgsz=640, opset=12, simplify=True)
print("[OK] Exported ${ONNX_NAME}")
PY

ls -lah "$ONNX_NAME"
