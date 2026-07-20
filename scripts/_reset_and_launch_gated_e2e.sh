#!/usr/bin/env bash
set -euo pipefail
ROOT=~/citevision-v2
cd "$ROOT"
sed -i 's/\r$//' scripts/_reset_demo_password.py
python3 scripts/_reset_demo_password.py 'Hologram2026!'
export ADMIN_PASSWORD='Hologram2026!'
export DEMO_MODE=1
export DEMO_EVIDENCE_BACKEND=strict_frigate
export DEMO_RESOLUTION=1080p
export LIVE_108_ENABLED=0
# Ensure validate script picks up the password (it defaults differently)
grep -q '^ADMIN_PASSWORD=' .env && sed -i 's|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=Hologram2026!|' .env || echo 'ADMIN_PASSWORD=Hologram2026!' >>.env
grep -q '^ADMIN_EMAIL=' .env || echo 'ADMIN_EMAIL=glory.henock@hologram.cd' >>.env
bash /mnt/c/Users/gheno/citevision/scripts/_launch_gated_e2e_wsl.sh
