#!/usr/bin/env bash
# Entry point for installer /api/launch and manual WSL start.
# Prefers native WSL tree ~/citevision-v2 when present (edits on /mnt/c are not runtime).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EDIT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

RUNTIME_ROOT=""
if [[ -n "${CV_ROOT:-}" && -f "${CV_ROOT}/scripts/lib/start-full-stack.sh" ]]; then
  RUNTIME_ROOT="$CV_ROOT"
elif [[ -f "${HOME}/citevision-v2/scripts/lib/start-full-stack.sh" ]]; then
  RUNTIME_ROOT="${HOME}/citevision-v2"
elif [[ "$EDIT_ROOT" != /mnt/c/* && "$EDIT_ROOT" != /mnt/d/* && -f "$EDIT_ROOT/scripts/lib/start-full-stack.sh" ]]; then
  RUNTIME_ROOT="$EDIT_ROOT"
else
  echo "[FAIL] Runtime root introuvable. Synchronisez vers \$HOME/citevision-v2 puis relancez." >&2
  echo "       EDIT_ROOT=$EDIT_ROOT (interdit sous /mnt/* pour le démarrage)" >&2
  exit 1
fi

export CV_ROOT="$RUNTIME_ROOT"
echo "[INFO] start-linux → RUNTIME_ROOT=$RUNTIME_ROOT"
exec bash "$RUNTIME_ROOT/scripts/lib/start-full-stack.sh"
