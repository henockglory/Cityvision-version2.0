#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="$ROOT/ai-engine/models"
IFACE_DIR="$MODEL_DIR/insightface"

mkdir -p "$MODEL_DIR" "$IFACE_DIR"

echo "==> Downloading YOLOv8n ONNX"
bash "$ROOT/scripts/download-yolo-model.sh"

echo "==> Downloading InsightFace buffalo_l"
if [ -d "$IFACE_DIR/models/buffalo_l" ] || [ -d "$HOME/.insightface/models/buffalo_l" ]; then
  echo "InsightFace buffalo_l already present"
else
  python3 - <<'PY'
import sys
from pathlib import Path
root = Path(sys.argv[1])
try:
    from insightface.app import FaceAnalysis
    app = FaceAnalysis(name="buffalo_l", root=str(root / "insightface"))
    app.prepare(ctx_id=-1)
    print("InsightFace buffalo_l downloaded")
except Exception as e:
    print(f"InsightFace download will complete on first run: {e}")
PY
"$IFACE_DIR"
fi

echo "==> Initializing PaddleOCR models"
python3 - <<'PY'
try:
    from paddleocr import PaddleOCR
    PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    print("PaddleOCR models ready")
except Exception as e:
    print(f"PaddleOCR will download on first run: {e}")
PY

echo "==> All models download step complete"
