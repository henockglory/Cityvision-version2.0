#!/usr/bin/env bash
# Quick phone-only validation: 1 detection, max 5 min.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

export RULE_TIMEOUT_SEC="${RULE_TIMEOUT_SEC:-300}"
export TARGET_DETECTIONS=1
export REPORT_TAG=phone-quick
export VALIDATE_ONLY="Démo · Téléphone au volant"

export PYTHONUNBUFFERED=1
exec python3 "$ROOT/scripts/validate_demo_five_rules.py"
