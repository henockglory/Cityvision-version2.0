#!/usr/bin/env bash
set -euo pipefail
ROOT=~/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Hologram2026!}"

echo "=== inject_faults_test ==="
bash scripts/inject_faults_test.sh

echo "=== validate_demo_five_rules (sequential, long) ==="
python3 scripts/validate_demo_five_rules.py
