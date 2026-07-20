#!/usr/bin/env bash
# Bench rapide OCR Fast-ALPR (port mono/scripts/ocr-bench-quick.sh)
set -euo pipefail
OCR_URL="${OCR_URL:-http://127.0.0.1:8181/ocr}"
echo "==> OCR bench $OCR_URL"
curl -fsS "${OCR_URL%/ocr}/healthz" && echo " healthz OK" || { echo "OCR indisponible"; exit 1; }
if [ -f "scripts/_diag/scene_check.jpg" ]; then
  curl -fsS -X POST -F "file=@scripts/_diag/scene_check.jpg" "$OCR_URL" | head -c 400
  echo
else
  echo "[skip] pas de scripts/_diag/scene_check.jpg"
fi
