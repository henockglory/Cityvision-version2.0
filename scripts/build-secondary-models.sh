#!/usr/bin/env bash
# Build or download secondary ONNX models (phone cls + seatbelt det).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VENV="${ROOT}/ai-engine/.venv/bin/python"
[[ -x "$VENV" ]] || VENV="$(command -v python3)"

# shellcheck source=scripts/lib/install-progress.sh
source "$ROOT/scripts/lib/install-progress.sh"

echo "=== build-secondary-models ==="

# 1) Sync rapide depuis le runtime WSL (évite pip + export ONNX sur /mnt/c).
sync_secondary_from_runtime "$ROOT"
if bash "$ROOT/scripts/download-secondary-models.sh"; then
  echo "[OK] Secondary models ready (sync runtime ou déjà présents)"
  exit 0
fi

log_slow_step \
  "Modèles secondaires manquants — construction locale (téléphone + ceinture)" \
  "Ordre : dépendances pip → export ONNX → vérification. 1ère fois : 10–30 min sur /mnt/c ; les lignes […] confirment que ça avance."

if "$VENV" -c "import ultralytics" 2>/dev/null; then
  echo "[OK] ultralytics déjà installé — skip pip"
else
  log_slow_step \
    "Étape 1/3 : pip install ultralytics + onnx" \
    "Peut prendre 5–20 min sur disque Windows (/mnt/c) — ce n'est pas un blocage."
  run_with_heartbeat 30 "pip ultralytics/onnx" \
    "$VENV" -m pip install ultralytics onnx
fi

export SEATBELT_PT_URL="${SEATBELT_PT_URL:-https://github.com/KorkanaRahul/Seatbelt-Detection-Using-DWYOLOv8-Model/raw/main/Weights/seatbeltWbest%20(1).pt}"
export SEATBELT_EPOCHS="${SEATBELT_EPOCHS:-20}"

log_slow_step \
  "Étape 2/3 : export ONNX (HuggingFace / poids publics)" \
  "Téléchargement + conversion — 2–15 min selon le réseau."

run_with_heartbeat 45 "export ONNX secondaires" \
  "$VENV" -u "$ROOT/ai-engine/scripts/build_secondary_models.py" "$@"

log_slow_step "Étape 3/3 : vérification fichiers ONNX"
if ! bash "$ROOT/scripts/download-secondary-models.sh" --fix; then
  echo "[FAIL] secondary models not ready"
  exit 1
fi

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
