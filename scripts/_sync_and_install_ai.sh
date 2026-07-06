#!/usr/bin/env bash
set -euo pipefail
WIN=/mnt/c/Users/gheno/citevision
DEST=~/citevision-v2
files=(
  scripts/lib/cuda-utils.sh
  scripts/install-ai-models.sh
  scripts/download-insightface.sh
  scripts/download-models.sh
  scripts/restart-api-frontend.sh
  scripts/download-secondary-models.sh
  scripts/run-ai-engine.sh
  scripts/_copy_working_cudnn.sh
  ai-engine/scripts/build_secondary_models.py
  ai-engine/scripts/verify_ai_stack.py
  ai-engine/src/citevision_ai/utils/paddle_ocr_compat.py
  ai-engine/src/citevision_ai/identity/plate.py
  ai-engine/src/citevision_ai/main.py
  shared/ai-stack-registry.json
)
for f in "${files[@]}"; do
  sed 's/\r$//' "$WIN/$f" > "$DEST/$f"
done
cd ~/citevision-v2
bash scripts/_copy_working_cudnn.sh 2>/dev/null || true
bash scripts/install-ai-models.sh "$@"
