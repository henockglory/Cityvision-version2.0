#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

# Health gates
curl -sf http://127.0.0.1:8081/health >/dev/null
curl -sf http://127.0.0.1:8001/health | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d.get("status")=="ok" and str(d.get("models_all_ok")).lower()=="true"'
curl -sf http://127.0.0.1:8010/health >/dev/null
echo "stack healthy"

cp -f /mnt/c/Users/gheno/citevision/scripts/_validate_rule_frigate_1hit.py "$ROOT/scripts/_validate_rule_frigate_1hit.py"
sed -i 's/\r$//' "$ROOT/scripts/_validate_rule_frigate_1hit.py"

export ADMIN_PASSWORD='Hologram2026!'
export RULE_NAME='Démo · Excès de vitesse'
export TARGET_DETECTIONS=1
export RULE_DURATION_SEC=600
export PYTHONUNBUFFERED=1

python3 scripts/_validate_rule_frigate_1hit.py
echo "EXIT=$?"
