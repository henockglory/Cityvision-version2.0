#!/usr/bin/env bash
# Wrapper for validate_demo_five_rules.py
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
export DEMO_ORG_ID="${DEMO_ORG_ID:-e312f375-7442-4089-8022-ed232abc09e8}"
exec python3 "$ROOT/scripts/validate_demo_five_rules.py" "$@"
