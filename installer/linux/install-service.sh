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
  if ! systemctl is-enabled --quiet citevision.service 2>/dev/null; then
    echo "[ERR]  Service not enabled after install (expected auto start)" >&2
    exit 1
  fi
  echo "[OK]   Service citevision.service registered - automatic startup enabled"
  echo "       State: $(systemctl is-active citevision.service 2>/dev/null || echo 'inactive')"
else
  systemctl disable citevision.service 2>/dev/null || true
  if systemctl is-enabled --quiet citevision.service 2>/dev/null; then
    echo "[ERR]  Service still enabled after switching to manual mode" >&2
    exit 1
  fi
  echo "[OK]   Service citevision.service registered - manual mode"
  echo "       Start: sudo systemctl start citevision"
  echo "       Stop:  sudo systemctl stop citevision"
fi

if [[ ! -f "$UNIT_PATH" ]]; then
  echo "[ERR]  Unit file missing after install: $UNIT_PATH" >&2
  exit 1
fi

# ── Sudoers drop-in: allow the app user to control the service without a
#    password prompt (needed for start/stop and auto/manual toggle from the UI).
SYSTEMCTL_BIN="$(command -v systemctl || echo /usr/bin/systemctl)"
SUDOERS_FILE="/etc/sudoers.d/citevision"
INSTALL_SCRIPT="$ROOT/installer/linux/install-service.sh"
{
  echo "# Managed by CitéVision install-service.sh - do not edit by hand"
  echo "$USER_NAME ALL=(root) NOPASSWD: $SYSTEMCTL_BIN start citevision.service, $SYSTEMCTL_BIN stop citevision.service, $SYSTEMCTL_BIN restart citevision.service, $SYSTEMCTL_BIN enable citevision.service, $SYSTEMCTL_BIN disable citevision.service"
  echo "$USER_NAME ALL=(root) NOPASSWD: /bin/bash $INSTALL_SCRIPT *"
} > "$SUDOERS_FILE"
chmod 440 "$SUDOERS_FILE"
if command -v visudo &>/dev/null && ! visudo -cf "$SUDOERS_FILE" &>/dev/null; then
  echo "[WARN] Sudoers drop-in invalid - removing $SUDOERS_FILE" >&2
  rm -f "$SUDOERS_FILE"
else
  echo "[OK]   Sudoers drop-in installed - UI can start/stop without password"
fi

echo "{\"service_ok\":true,\"start_mode\":\"$START_MODE\",\"service\":\"citevision.service\"}"
