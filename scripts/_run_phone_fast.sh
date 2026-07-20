#!/usr/bin/env bash
set -uo pipefail
cd ~/citevision-v2
source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file ~/citevision-v2)"
export ADMIN_EMAIL=glory.henock@hologram.cd
export ADMIN_PASSWORD='Hologram2026!'
export DEMO_ORG_ID=74d51ead-97a7-4e41-a488-503a9b90c466
export INTERNAL_API_KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
export RULE_PREFLIGHT_STRICT=1
export SYNC_WAIT=15
export RULE_TIMEOUT_SEC=300
export ALERT_WAIT_SEC=180
export VALIDATE_ONLY='Démo · Téléphone au volant'
export REPORT_TAG=phone-fast
curl -sf http://127.0.0.1:8001/health >/dev/null || bash scripts/restart-ai-engine.sh
python3 -u scripts/validate_demo_five_rules.py
