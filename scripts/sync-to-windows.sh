#!/usr/bin/env bash
# Synchronise WSL ~/citevision-v2/ → Windows C:/Users/gheno/citevision-v2/
# Exclut les artefacts volumineux (node_modules, .venv, *.pyc, build)
set -euo pipefail
SRC="$HOME/citevision-v2/"
DST="/mnt/c/Users/gheno/citevision-v2/"

if [ ! -d "$DST" ]; then
    echo "[WARN] Dossier Windows introuvable: $DST"
    exit 1
fi

echo "=== Sync WSL → Windows ==="
rsync -av --checksum --delete \
    --exclude='.git/' \
    --exclude='node_modules/' \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='.mypy_cache/' \
    --exclude='dist/' \
    --exclude='build/' \
    --exclude='*.egg-info/' \
    --exclude='models/*.onnx' \
    "$SRC" "$DST"
echo "=== Sync terminé ==="
