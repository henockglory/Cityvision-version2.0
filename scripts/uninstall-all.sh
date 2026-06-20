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
      echo "[INFO] Mode restart — redémarrage des services uniquement"
      echo "[INFO] Arrêt des services…"
      bash scripts/stop-linux.sh || true
      echo "[INFO] Redémarrage des services…"
      bash scripts/start-linux.sh || true
      echo "[OK]   Services redémarrés"
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
echo "=== CitéVision v2 — Désinstallation ==="

# 1. Arrêt des services
echo "[INFO] Arrêt des services…"
bash scripts/stop-linux.sh || true

# 2. Service Linux (systemd)
if command -v systemctl &>/dev/null; then
  echo "[INFO] Suppression service systemd…"
  sudo bash installer/linux/uninstall-service.sh 2>/dev/null || true
fi

# 3. Service Windows (WSL)
if grep -qi microsoft /proc/version 2>/dev/null && command -v powershell.exe &>/dev/null; then
  echo "[INFO] Suppression service Windows (NSSM)…"
  powershell.exe -NoProfile -ExecutionPolicy Bypass \
    -File "$ROOT/installer/windows/uninstall-service.ps1" 2>/dev/null || true
fi

# 4. Docker
if [[ "$KEEP_DATA" == "true" ]]; then
  echo "[INFO] Docker compose down (volumes conservés)…"
  docker compose -f infra/docker-compose.yml down 2>/dev/null || true
else
  echo "[INFO] Docker compose down -v (suppression volumes)…"
  docker compose -f infra/docker-compose.yml down -v 2>/dev/null || true
fi

# 5. Sentinelles
rm -f ai-engine/.venv/.installed_ok installer/.service_start_mode 2>/dev/null || true

# 6. Purge dépendances (from-scratch, mais pas si keep-deps)
if [[ "$FROM_SCRATCH" == "true" && "$KEEP_DEPS" != "true" ]]; then
  echo "[INFO] Purge from-scratch (venv, node_modules, logs)…"
  rm -rf ai-engine/.venv frontend/node_modules 2>/dev/null || true
  rm -f generated.env 2>/dev/null || true
  rm -f logs/*.log logs/*.pid 2>/dev/null || true
  # Purge venv ext4 WSL si présent
  if [[ -d "$HOME/.citevision-v2" ]]; then
    echo "[INFO] Purge venv ext4 WSL (~/.citevision-v2)…"
    rm -rf "$HOME/.citevision-v2" 2>/dev/null || true
  fi
  echo "[OK]   Purge from-scratch terminée"
fi

# 7. Données utilisateur (mode nuclear)
if [[ "$DELETE_USER_DATA" == "true" ]]; then
  echo "[INFO] Suppression données utilisateur (vidéos, preuves)…"
  rm -rf data/videos data/evidence 2>/dev/null || true
  echo "[OK]   Données utilisateur supprimées"
fi

echo ""
echo "[OK]   Désinstallation terminée"
echo "[INFO] Pour réinstaller : lancez setup.bat (Windows) ou bash scripts/setup-wsl.sh"
echo ""
exit 0
