#!/usr/bin/env bash
set -euo pipefail
WIN=/mnt/c/Users/gheno/citevision
DEST=~/citevision-v2
cp "$WIN/scripts/install-ai-models.sh" "$DEST/scripts/"
cp "$WIN/scripts/download-models.sh" "$DEST/scripts/"
cp "$WIN/scripts/run-ai-engine.sh" "$DEST/scripts/"
cp "$WIN/scripts/build-secondary-models.sh" "$DEST/scripts/"
cp "$WIN/scripts/download-secondary-models.sh" "$DEST/scripts/"
cp "$WIN/scripts/ensure-ai-stack.sh" "$DEST/scripts/"
cp "$WIN/scripts/lib/cuda-utils.sh" "$DEST/scripts/lib/"
cp "$WIN/shared/"*.json "$DEST/shared/"
cp -r "$WIN/ai-engine/src" "$DEST/ai-engine/"
cp "$WIN/ai-engine/scripts/verify_ai_stack.py" "$DEST/ai-engine/scripts/"
for f in install-ai-models.sh download-models.sh run-ai-engine.sh build-secondary-models.sh download-secondary-models.sh ensure-ai-stack.sh lib/cuda-utils.sh; do
  sed -i 's/\r$//' "$DEST/scripts/$f"
done
cd "$DEST"
source ai-engine/.venv/bin/activate
pip install -q -e ai-engine/.
bash scripts/install-ai-models.sh --fix
