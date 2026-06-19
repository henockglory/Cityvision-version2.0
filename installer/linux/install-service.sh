#!/usr/bin/env bash
# CitéVision v2 — Enregistrement du service systemd citevision.service
# Usage: sudo bash installer/linux/install-service.sh --root=/path --user=username [--start-mode=auto|manual]
set -euo pipefail

ROOT=""
USER_NAME=""
START_MODE="auto"
TEMPLATE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/citevision.service"
UNIT_PATH="/etc/systemd/system/citevision.service"

for arg in "$@"; do
  case "$arg" in
    --root=*)       ROOT="${arg#*=}" ;;
    --user=*)       USER_NAME="${arg#*=}" ;;
    --start-mode=*) START_MODE="${arg#*=}" ;;
    --help)
      echo "Usage: sudo bash installer/linux/install-service.sh --root=/path --user=username [--start-mode=auto|manual]"
      exit 0
      ;;
    *)
      echo "[WARN] Argument inconnu: $arg" >&2
      ;;
  esac
done

if [[ -z "$ROOT" ]]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fi
if [[ -z "$USER_NAME" ]]; then
  USER_NAME="$(whoami)"
fi
if [[ "$START_MODE" != "auto" && "$START_MODE" != "manual" ]]; then
  echo "[ERR]  --start-mode doit être 'auto' ou 'manual'" >&2
  exit 1
fi

if ! command -v systemctl &>/dev/null; then
  echo "[WARN] systemd non disponible — service citevision.service non enregistré"
  exit 1
fi

if [[ ! -f "$TEMPLATE" ]]; then
  echo "[ERR]  Template introuvable: $TEMPLATE" >&2
  exit 1
fi

if [[ $EUID -ne 0 ]]; then
  echo "[ERR]  Droits root requis — lancez: sudo bash $0 --root=$ROOT --user=$USER_NAME --start-mode=$START_MODE" >&2
  exit 1
fi

# Générer l'unité systemd depuis le template
sed -e "s|__ROOT__|$ROOT|g" -e "s|__USER__|$USER_NAME|g" "$TEMPLATE" > "$UNIT_PATH"
chmod 644 "$UNIT_PATH"

systemctl daemon-reload

if [[ "$START_MODE" == "auto" ]]; then
  systemctl enable citevision.service
  if ! systemctl is-active --quiet citevision.service 2>/dev/null; then
    systemctl start citevision.service || true
  fi
  echo "[OK]   Service citevision.service enregistré — démarrage automatique activé"
  echo "       État: $(systemctl is-active citevision.service 2>/dev/null || echo 'inactive')"
else
  systemctl disable citevision.service 2>/dev/null || true
  echo "[OK]   Service citevision.service enregistré — mode manuel"
  echo "       Démarrer: sudo systemctl start citevision"
  echo "       Arrêter:  sudo systemctl stop citevision"
fi
