#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# CitéVision v2 — Désinstallation complète
#
# Usage:
#   bash scripts/uninstall-all.sh [--keep-data] [--yes]
#
# Options:
#   --keep-data   Conserve les volumes Docker (données applicatives)
#   --yes         Mode non interactif
# ─────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

KEEP_DATA=false
ASSUME_YES=false

for arg in "$@"; do
  case "$arg" in
    --keep-data) KEEP_DATA=true ;;
    --yes) ASSUME_YES=true ;;
    --help)
      cat <<'EOF'
Usage: bash scripts/uninstall-all.sh [OPTIONS]

Désinstalle CitéVision v2 : arrêt services, suppression service système,
Docker down (volumes supprimés par défaut).

Options:
  --keep-data   Conserve les volumes Docker
  --yes         Sans confirmation interactive
  --help        Afficher cette aide
EOF
      exit 0
      ;;
    *)
      echo "[WARN] Argument inconnu: $arg" >&2
      ;;
  esac
done

if [[ "$ASSUME_YES" != "true" ]]; then
  echo ""
  echo "=== CitéVision v2 — Désinstallation ==="
  if [[ "$KEEP_DATA" == "true" ]]; then
    echo "Les volumes Docker seront CONSERVÉS."
  else
    echo "ATTENTION : les volumes Docker seront SUPPRIMÉS (données perdues)."
  fi
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

echo ""
echo "[OK]   Désinstallation terminée"
echo "[INFO] Pour réinstaller : lancez setup.bat (Windows) ou bash scripts/setup-wsl.sh"
echo ""
exit 0
