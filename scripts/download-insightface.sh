#!/usr/bin/env bash
# Download InsightFace buffalo_l pack into ai-engine/models/insightface/
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IFACE_ROOT="$ROOT/ai-engine/models/insightface"
ONNX_DIR="$IFACE_ROOT/models/buffalo_l"
PYTHON="${ROOT}/ai-engine/.venv/bin/python3"
MIN_ONNX="${MIN_INSIGHTFACE_ONNX:-3}"

mkdir -p "$ONNX_DIR"
count=0
if [[ -d "$ONNX_DIR" ]]; then
  count="$(find "$ONNX_DIR" -name '*.onnx' 2>/dev/null | wc -l | tr -d ' ')"
fi
if [[ "$count" -ge "$MIN_ONNX" ]]; then
  echo "[OK] InsightFace buffalo_l ($count onnx)"
  exit 0
fi

# Sync from user cache
if [[ -d "$HOME/.insightface/models/buffalo_l" ]]; then
  cp -a "$HOME/.insightface/models/buffalo_l/"*.onnx "$ONNX_DIR/" 2>/dev/null || true
  count="$(find "$ONNX_DIR" -name '*.onnx' 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "$count" -ge "$MIN_ONNX" ]]; then
    echo "[OK] InsightFace synced from ~/.insightface ($count onnx)"
    exit 0
  fi
fi

echo "==> Downloading buffalo_l.zip (InsightFace release)…"
ZIP="$IFACE_ROOT/buffalo_l.zip"
URL="${INSIGHTFACE_BUFFALO_URL:-https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip}"
if curl -fSL --retry 3 -o "$ZIP" "$URL"; then
  rm -rf "$ONNX_DIR"
  mkdir -p "$ONNX_DIR"
  unzip -o -q "$ZIP" -d "$ONNX_DIR"
  # Some archives flatten files — also accept models/*.onnx at parent level.
  shopt -s nullglob
  for f in "$IFACE_ROOT/models"/*.onnx; do
    mv "$f" "$ONNX_DIR/"
  done
  rm -f "$ZIP"
  count="$(find "$ONNX_DIR" -name '*.onnx' 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "$count" -ge "$MIN_ONNX" ]]; then
    echo "[OK] InsightFace buffalo_l from zip ($count onnx)"
    exit 0
  fi
  # Retry: zip may contain a buffalo_l/ subfolder
  if [[ -d "$IFACE_ROOT/models/buffalo_l" ]] && [[ "$ONNX_DIR" != "$IFACE_ROOT/models/buffalo_l" ]]; then
    mv "$IFACE_ROOT/models/buffalo_l/"*.onnx "$ONNX_DIR/" 2>/dev/null || true
  fi
  count="$(find "$ONNX_DIR" -name '*.onnx' 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "$count" -ge "$MIN_ONNX" ]]; then
    echo "[OK] InsightFace buffalo_l from zip ($count onnx)"
    exit 0
  fi
fi

echo "==> Fallback: insightface FaceAnalysis auto-download…"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
"$PYTHON" - <<PY
import sys
from pathlib import Path
root = Path("${IFACE_ROOT}")
try:
    from insightface.app import FaceAnalysis
    app = FaceAnalysis(name="buffalo_l", root=str(root), providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(640, 640))
    onnx = list((root / "models" / "buffalo_l").glob("*.onnx"))
    if len(onnx) < ${MIN_ONNX}:
        raise SystemExit(f"only {len(onnx)} onnx after FaceAnalysis")
    print(f"[OK] InsightFace via FaceAnalysis ({len(onnx)} onnx)")
except Exception as e:
    raise SystemExit(f"[ERR] InsightFace download failed: {e}") from e
PY
