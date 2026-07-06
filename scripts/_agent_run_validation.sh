#!/usr/bin/env bash
# Run the E2E demo validation on the 4 currently-failing rules (speed excluded),
# with the new mono-camera switching. Read-only vs geometry; only toggles rules
# and the active demo camera via the API (same as the UI).
set -uo pipefail
export ADMIN_EMAIL="glory.henock@hologram.cd"
export ADMIN_PASSWORD='Henockglory@03'
export TARGET_DETECTIONS=2
export RULE_TIMEOUT_SEC=420
export DEMO_SETTLE_SEC=20
export RULE_SYNC_WAIT_SEC=35
export REPORT_TAG=tuning
export VALIDATE_ONLY="Démo · Non-port ceinture,Démo · Excès de vitesse,Démo · Feu rouge"

cd /mnt/c/Users/gheno/citevision || exit 1
echo "== START validation $(date -u +%H:%M:%S) =="
python3 -u scripts/validate_demo_five_rules.py
echo "== END validation $(date -u +%H:%M:%S) rc=$? =="
