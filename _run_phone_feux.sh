#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2

# Run only "Téléphone au volant" and "Feux rouges" from the validation script
python3 scripts/validate_demo_five_rules.py \
  --rules "Démo · Téléphone au volant" "Démo · Feux rouges" \
  2>&1 | tee /tmp/phone_feux_run.log
