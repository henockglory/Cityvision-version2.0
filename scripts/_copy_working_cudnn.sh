#!/usr/bin/env bash
# Copie libcudnn depuis un venv CUDA fonctionnel si le venv courant est incomplet.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/wsl-root.sh
source "$ROOT/scripts/lib/wsl-root.sh"

VENV_DIR="$(resolve_venv_dir)"
DST="$VENV_DIR/lib/python3.12/site-packages/nvidia/cudnn/lib"
[[ -d "$DST" ]] || mkdir -p "$DST"

if [[ -f "$DST/libcudnn.so.9" ]]; then
  exit 0
fi

for SRC in \
  "${HOME}/citevision-v2/ai-engine/.venv/lib/python3.12/site-packages/nvidia/cudnn/lib" \
  "${HOME}/.citevision-v2/ai-engine-venv/lib/python3.12/site-packages/nvidia/cudnn/lib" \
  "/mnt/c/Users/gheno/citevision/ai-engine/.venv/lib/python3.12/site-packages/nvidia/cudnn/lib" \
  "/mnt/c/Users/gheno/citevision-v2/ai-engine/.venv/lib/python3.12/site-packages/nvidia/cudnn/lib"; do
  if [[ -f "$SRC/libcudnn.so.9" ]]; then
    echo "[FIX] Sync cuDNN depuis $SRC"
    mkdir -p "$DST"
    cp -a "$SRC"/. "$DST"/
    exit 0
  fi
done

echo "[WARN] cuDNN source introuvable — pip install nvidia-cudnn-cu12 via install-ai-models.sh --fix"
exit 0
