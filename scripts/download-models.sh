#!/usr/bin/env bash
# Télécharge les modèles IA requis : YOLO, InsightFace (buffalo_l), PaddleOCR
# Usage: bash scripts/download-models.sh [--skip-yolo]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="$ROOT/ai-engine/models"
IFACE_DIR="$MODEL_DIR/insightface"
SKIP_YOLO=false

for arg in "$@"; do
  case "$arg" in
    --skip-yolo) SKIP_YOLO=true ;;
    --help)
      echo "Usage: bash scripts/download-models.sh [--skip-yolo]"
      exit 0
      ;;
  esac
done

PYTHON="$ROOT/ai-engine/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3.12 || command -v python3 || echo python3)"
fi

mkdir -p "$MODEL_DIR" "$IFACE_DIR"

if [[ "$SKIP_YOLO" == "false" ]]; then
  echo "==> Downloading YOLO model"
  bash "$ROOT/scripts/download-yolo-model.sh"
else
  echo "==> Skipping YOLO download (--skip-yolo)"
fi

echo "==> Downloading InsightFace buffalo_l"
if [[ -d "$IFACE_DIR/models/buffalo_l" ]] || [[ -d "$HOME/.insightface/models/buffalo_l" ]]; then
  echo "[OK] InsightFace buffalo_l already present"
else
  if ! "$PYTHON" -c "import insightface" 2>/dev/null; then
    echo "[ERR] insightface not installed — run: pip install -e 'ai-engine/.[identity]'" >&2
    exit 1
  fi
  "$PYTHON" - <<PY
from pathlib import Path
root = Path("${ROOT}")
try:
    from insightface.app import FaceAnalysis
    app = FaceAnalysis(name="buffalo_l", root=str(root / "ai-engine" / "models" / "insightface"))
    app.prepare(ctx_id=-1)
    print("[OK] InsightFace buffalo_l downloaded")
except Exception as e:
    raise SystemExit(f"[ERR] InsightFace download failed: {e}")
PY
fi

echo "==> Initializing PaddleOCR models"
if ! "$PYTHON" -c "import paddleocr" 2>/dev/null; then
  echo "[ERR] paddleocr not installed — run: pip install -e 'ai-engine/.[anpr]'" >&2
  exit 1
fi
"$PYTHON" - <<'PY'
try:
    from paddleocr import PaddleOCR
    PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    print("[OK] PaddleOCR models ready")
except Exception as e:
    raise SystemExit(f"[ERR] PaddleOCR init failed: {e}")
PY

echo "==> All AI models download step complete"
