#!/usr/bin/env bash
# Apply permanent Demo5 validation env keys (installer / auto-fix hook).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="${1:-$ROOT/.env}"
ensure_demo_validation_env "$ROOT" "$ENV_FILE"
echo "[OK] ensure-demo-validation-env"
