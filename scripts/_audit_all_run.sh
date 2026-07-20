#!/usr/bin/env bash
set -uo pipefail
ROOT=/mnt/c/Users/gheno/citevision/scripts
for f in _audit_disk_wsl.sh _audit_frigate_live.sh _audit_cameras_db.sh _audit_events_mail.sh _audit_validation_debt.sh; do
  sed -i 's/\r$//' "$ROOT/$f"
done
echo "######## DISK ########"
bash "$ROOT/_audit_disk_wsl.sh"
echo "######## FRIGATE ########"
bash "$ROOT/_audit_frigate_live.sh"
echo "######## CAMERAS ########"
bash "$ROOT/_audit_cameras_db.sh"
echo "######## EVENTS MAIL ########"
bash "$ROOT/_audit_events_mail.sh"
echo "######## VALIDATION DEBT ########"
bash "$ROOT/_audit_validation_debt.sh"
