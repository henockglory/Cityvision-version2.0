#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# CitéVision v2 — Lanceur d'installation Linux / macOS
# Usage: chmod +x setup.sh && ./setup.sh
# Prérequis : Python 3.10+, connexion Internet
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=7315

echo ""
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║         CitéVision v2  —  Installateur               ║"
echo "  ║   Plateforme d'analyse vidéo intelligente             ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo ""

# ── 1. Trouver Python ────────────────────────────────────────
PYTHON=""
for candidate in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c "import sys; print(sys.version_info[:2])" 2>/dev/null || echo "(0, 0)")
        if [[ "$ver" > "(3, 9)" ]]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[ERREUR] Python 3.10+ introuvable."
    echo ""
    echo "  Ubuntu/Debian : sudo apt-get install -y python3.12"
    echo "  macOS         : brew install python@3.12"
    echo ""
    exit 1
fi

PY_VER=$($PYTHON --version 2>&1)
echo "  [INFO] Python détecté : $PY_VER"

# ── 2. Vérifier le port ───────────────────────────────────────
if lsof -ti:$PORT &>/dev/null; then
    echo "  [INFO] Port $PORT déjà occupé — tentative de reconnexion…"
    # Check if it's our installer
    if curl -sf "http://localhost:$PORT/api/status" &>/dev/null; then
        echo "  [INFO] Serveur d'installation déjà actif."
        BROWSER_URL="http://localhost:$PORT"
    else
        echo "  [WARN] Port $PORT occupé par un autre processus."
        PORT=$((PORT + 1))
        echo "  [INFO] Utilisation du port $PORT"
    fi
fi

BROWSER_URL="http://localhost:$PORT"

# ── 3. Ouvrir navigateur ──────────────────────────────────────
open_browser() {
    sleep 1.5
    if command -v xdg-open &>/dev/null; then
        xdg-open "$1" &>/dev/null &
    elif command -v open &>/dev/null; then
        open "$1" &>/dev/null &
    elif command -v wslview &>/dev/null; then
        wslview "$1" &>/dev/null &
    else
        echo "  [INFO] Ouvrez manuellement : $1"
    fi
}

echo "  [INFO] Démarrage du serveur d'installation sur $BROWSER_URL…"
echo "  [INFO] L'interface s'ouvrira automatiquement dans votre navigateur."
echo ""
echo "  Appuyez sur Ctrl+C pour arrêter."
echo ""

open_browser "$BROWSER_URL" &

cd "$SCRIPT_DIR"
exec "$PYTHON" installer/setup-server.py
