#!/usr/bin/env bash
# CitéVision v2 — Suppression du service systemd citevision.service
set -euo pipefail

if ! command -v systemctl &>/dev/null; then
  echo "[WARN] systemd non disponible"
  exit 0
fi

if [[ $EUID -ne 0 ]]; then
  echo "[ERR]  Droits root requis — lancez: sudo bash $0" >&2
  exit 1
fi

systemctl stop citevision.service 2>/dev/null || true
systemctl disable citevision.service 2>/dev/null || true
rm -f /etc/systemd/system/citevision.service
systemctl daemon-reload
echo "[OK]   Service citevision.service supprimé"
