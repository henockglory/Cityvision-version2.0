#!/usr/bin/env bash
# URGENCE : Synchronise Windows → WSL (seulement si WSL est en retard)
# Utiliser uniquement quand nécessaire — WSL est la source de vérité !
set -euo pipefail
SRC="/mnt/c/Users/gheno/citevision-v2/"
DST="$HOME/citevision-v2/"

echo "[WARN] Vous êtes sur le point de remplacer des fichiers WSL par des fichiers Windows."
echo "[WARN] Cela devrait être TRÈS rare. WSL est la source de vérité."
read -r -p "Continuer? (oui/non): " yn
if [ "$yn" != "oui" ]; then
    echo "Annulé."
    exit 0
fi

echo "=== Sync Windows → WSL (urgence) ==="
rsync -av --checksum \
    --exclude='.git/' \
    --exclude='node_modules/' \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='dist/' \
    --exclude='build/' \
    --exclude='models/*.onnx' \
    "$SRC" "$DST"
echo "=== Sync terminé — valider les fichiers critiques ==="
python3 scripts/validate_json.py frontend/src/i18n/fr.json
