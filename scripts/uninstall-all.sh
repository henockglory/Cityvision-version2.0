#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# CitéVision v2 — Désinstallation (5 modes)
#
# Usage:
#   bash scripts/uninstall-all.sh [OPTIONS]
#
# Modes (via --mode=) :
#   restart       Redémarre uniquement les services (stop + start)
#   soft          Arrêt + reset config (conserve volumes, venv, node_modules)
#   standard      Arrêt + suppression volumes Docker (conserve venv, node_modules)
#   full          Suppression complète sauf données utilisateur (default)
#   nuclear       Suppression totale absolue (données comprises)
#
# Options legacy (rétrocompat) :
#   --keep-data   Conserve les volumes Docker (≈ mode standard)
#   --from-scratch Supprime venv, node_modules, logs (≈ mode full)
#   --keep-deps   Conserve venv Python et node_modules
#   --delete-user-data  Supprime data/videos et data/evidence (~nuclear)
#   --yes         Mode non interactif
# ─────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE=""
KEEP_DATA=false
FROM_SCRATCH=false
KEEP_DEPS=false
DELETE_USER_DATA=false
ASSUME_YES=false

for arg in "$@"; do
  case "$arg" in
    --mode=*) MODE="${arg#*=}" ;;
    --keep-data) KEEP_DATA=true ;;
    --from-scratch) FROM_SCRATCH=true ;;
    --keep-deps) KEEP_DEPS=true ;;
    --delete-user-data) DELETE_USER_DATA=true ;;
    --yes) ASSUME_YES=true ;;
    --help)
      cat <<'EOF'
Usage: bash scripts/uninstall-all.sh [--mode=MODE] [OPTIONS]

Modes :
  restart    Redémarre les services seulement (rien supprimé)
  soft       Arrêt services + reset sentinelles (conserve tout le reste)
  standard   Arrêt + suppression volumes Docker (conserve venv + node_modules)
  full       Suppression venv + node_modules + volumes (conserve data utilisateur)
  nuclear    Suppression totale y compris données utilisateur

Options :
  --keep-data          Conserve les volumes Docker
  --from-scratch       Supprime venv, node_modules, logs
  --keep-deps          Conserve venv Python et node_modules
  --delete-user-data   Supprime data/videos et data/evidence
  --yes                Sans confirmation interactive
EOF
      exit 0
      ;;
    *)
      echo "[WARN] Argument inconnu: $arg" >&2
      ;;
  esac
done

# Résoudre les flags depuis --mode si fourni
if [[ -n "$MODE" ]]; then
  case "$MODE" in
    restart)
      echo "[INFO] Mode restart - redemarrage des services uniquement"
      echo "[INFO] Lancement du stop+start en arriere-plan detache..."
      # Use setsid to detach from process group so the backend can send the final SSE event
      # before being killed by stop-linux.sh
      RESTART_LOG="/tmp/citevision-restart.log"
      setsid bash -c "sleep 2; bash '${ROOT}/scripts/stop-linux.sh' > '${RESTART_LOG}' 2>&1; sleep 3; bash '${ROOT}/scripts/start-linux.sh' >> '${RESTART_LOG}' 2>&1" &
      echo "[OK]   Redemarrage programme - les services redemarreront dans ~5 secondes"
      echo "[INFO] Log: ${RESTART_LOG}"
      exit 0
      ;;
    soft)
      KEEP_DATA=true; KEEP_DEPS=true ;;
    standard)
      KEEP_DEPS=true ;;
    full)
      FROM_SCRATCH=true ;;
    nuclear)
      FROM_SCRATCH=true; DELETE_USER_DATA=true ;;
    *)
      echo "[WARN] Mode inconnu '$MODE', utilisation du mode full" >&2
      FROM_SCRATCH=true ;;
  esac
fi

if [[ "$ASSUME_YES" != "true" ]]; then
  echo ""
  echo "=== CitéVision v2 — Désinstallation ==="
  if [[ "$KEEP_DATA" == "true" ]]; then
    echo "Les volumes Docker seront CONSERVÉS."
  else
    echo "ATTENTION : les volumes Docker seront SUPPRIMÉS (données perdues)."
  fi
  [[ "$DELETE_USER_DATA" == "true" ]] && echo "ATTENTION : les données utilisateur (vidéos, preuves) seront SUPPRIMÉES."
  read -r -p "Continuer ? [o/N] " ans
  case "${ans,,}" in
    o|oui|y|yes) ;;
    *) echo "Annulé."; exit 0 ;;
  esac
fi

echo ""
echo "=== CitevisionV2 - Uninstall ==="

# --- Do all non-disruptive work FIRST so backend can stream it ---
# The backend process will be killed in the final step; by doing cleanup
# before stopping services, we ensure the SSE stream captures all events.

# 1. Sentinelles
echo "[INFO] Removing sentinels..."
rm -f ai-engine/.venv/.installed_ok installer/.service_start_mode 2>/dev/null || true
echo "[OK]   Sentinels removed"

# 2. Service Linux (systemd) - non-disruptive if app isn't registered as systemd service
if command -v systemctl &>/dev/null; then
  echo "[INFO] Removing systemd service..."
  sudo bash installer/linux/uninstall-service.sh 2>/dev/null || true
fi

# 3. Service Windows (WSL) - non-disruptive to the backend process
if grep -qi microsoft /proc/version 2>/dev/null && command -v powershell.exe &>/dev/null; then
  echo "[INFO] Removing Windows service (NSSM)..."
  powershell.exe -NoProfile -ExecutionPolicy Bypass \
    -File "$ROOT/installer/windows/uninstall-service.ps1" 2>/dev/null || true
fi

# 4. Purge dependencies (from-scratch, but not if keep-deps)
if [[ "$FROM_SCRATCH" == "true" && "$KEEP_DEPS" != "true" ]]; then
  echo "[INFO] Full purge (venv, node_modules, logs)..."
  rm -rf ai-engine/.venv frontend/node_modules 2>/dev/null || true
  rm -f generated.env 2>/dev/null || true
  rm -f logs/*.log logs/*.pid 2>/dev/null || true
  if [[ -d "$HOME/.citevision-v2" ]]; then
    echo "[INFO] Purging WSL ext4 venv (~/.citevision-v2)..."
    rm -rf "$HOME/.citevision-v2" 2>/dev/null || true
  fi
  echo "[OK]   Full purge done"
fi

# 5. User data (nuclear mode)
if [[ "$DELETE_USER_DATA" == "true" ]]; then
  echo "[INFO] Removing user data (videos, evidence)..."
  rm -rf data/videos data/evidence 2>/dev/null || true
  echo "[OK]   User data removed"
fi

# 6. Docker - run while backend is still alive to capture output
if [[ "$KEEP_DATA" == "true" ]]; then
  echo "[INFO] Docker compose down (volumes kept)..."
  docker compose -f infra/docker-compose.yml down 2>/dev/null || true
else
  echo "[INFO] Docker compose down -v (removing volumes)..."
  docker compose -f infra/docker-compose.yml down -v 2>/dev/null || true
fi
echo "[OK]   Docker stopped"

echo ""
echo "[OK]   Cleanup complete - stopping services now..."
echo "[INFO] Connection will be lost when services stop. This is expected."
echo ""

# 7. Stop running services LAST (this kills the backend - do it detached)
# Use setsid to detach from process group so the backend can send the final
# SSE event before being killed. The 1s sleep gives the backend time to flush.
setsid bash -c "sleep 1; bash '${ROOT}/scripts/stop-linux.sh'" > /tmp/citevision-stop.log 2>&1 &

echo "[OK]   Uninstall complete"
echo "[INFO] To reinstall: run setup.bat (Windows) or bash scripts/setup-wsl.sh (Linux)"
echo ""
exit 0
