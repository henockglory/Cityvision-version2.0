#!/usr/bin/env bash
# Télécharge les modèles IA primaires : YOLO, InsightFace (buffalo_l), PaddleOCR.
# Les modèles secondaires (phone, seatbelt) sont construits par install-ai-models.sh
# via build-secondary-models.sh — pas ici (pas d'URL de téléchargement directe).
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
PIP="$ROOT/ai-engine/.venv/bin/pip"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3.12 || command -v python3 || echo python3)"
  PIP="$(command -v pip3 || command -v pip || echo pip3)"
fi

_ensure_pip_extra() {
  local module="$1"
  local extra="$2"
  if ! "$PYTHON" -c "import $module" 2>/dev/null; then
    echo "[FIX] Auto-install pip extra [$extra] pour $module…"
    "$PIP" install -e "$ROOT/ai-engine/.[identity,anpr,dev]" 2>/dev/null \
      || "$PIP" install --no-cache-dir -e "$ROOT/ai-engine/.[identity,anpr,dev]"
  fi
}

mkdir -p "$MODEL_DIR" "$IFACE_DIR"

if [[ "$SKIP_YOLO" == "false" ]]; then
  echo "==> Downloading YOLO model"
  bash "$ROOT/scripts/download-yolo-model.sh"
else
  echo "==> Skipping YOLO download (--skip-yolo)"
fi

echo "==> Downloading InsightFace buffalo_l"
_ensure_pip_extra insightface identity
bash "$ROOT/scripts/download-insightface.sh"

echo "==> Initializing PaddleOCR models"
_ensure_pip_extra paddleocr anpr
if ! "$PYTHON" -c "import paddleocr" 2>/dev/null; then
  echo "[FIX] pip install anpr extras…"
  "$PIP" install --no-cache-dir -e "$ROOT/ai-engine/.[identity,anpr,dev]"
fi
"$PYTHON" - <<'PY'
try:
    import numpy as np
    from citevision_ai.utils.paddle_ocr_compat import create_paddle_ocr, parse_ocr_lines, run_ocr
    ocr = create_paddle_ocr()
    run_ocr(ocr, np.zeros((48, 160, 3), dtype=np.uint8))
    parse_ocr_lines([])
    print("[OK] PaddleOCR models ready + inference smoke ok")
except Exception as e:
    raise SystemExit(f"[ERR] PaddleOCR init failed: {e}")
PY

echo "==> Primary models download step complete"
