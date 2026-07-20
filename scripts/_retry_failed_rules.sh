#!/usr/bin/env bash
set -euo pipefail
ROOT=~/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Hologram2026!}"
export VALIDATE_ONLY="Démo · Excès de vitesse,Démo · Téléphone au volant,Démo · Feu rouge"
export ALERT_WAIT_SEC=180
export DEMO_SETTLE_SEC=50
cp /mnt/c/Users/gheno/citevision/scripts/validate_demo_five_rules.py scripts/
sed -i 's/\r$//' scripts/validate_demo_five_rules.py
python3 scripts/validate_demo_five_rules.py
