#!/usr/bin/env bash
set -uo pipefail
ROOT=~/citevision-v2
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
cd "$ROOT"
source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"

cp /mnt/c/Users/gheno/citevision/scripts/validate_demo_five_rules.py scripts/
sed -i 's/\r$//' scripts/validate_demo_five_rules.py

# Stop physical RTSP camera hogging orchestrator
curl -sf -X POST http://127.0.0.1:8001/cameras/d2eb7076-c3b3-40fd-9b2c-0d119bb975c9/stop || true
curl -sf -X POST http://127.0.0.1:8001/cameras/55694d53-8f58-4981-91b2-7c6cd528a25d/stop || true
sleep 3

export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Hologram2026!}"
export DEMO_ORG_ID=74d51ead-97a7-4e41-a488-503a9b90c466
export VALIDATE_ONLY="Démo · Téléphone au volant"
export DEMO_MIN_FRAMES=10
export DEMO_READY_TIMEOUT_SEC=240
export FRIGATE_EVENTS_WAIT_SEC=120
export ALERT_WAIT_SEC=240
export RULE_TIMEOUT_SEC=600

python3 scripts/validate_demo_five_rules.py 2>&1 | tee logs/validate-phone-retry.log
exit ${PIPESTATUS[0]}
