#!/usr/bin/env bash
# Manual demo checklist: health, spatial reload, speed rule E2E (alert + full evidence + mail).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

export DEMO_ORG_ID="${DEMO_ORG_ID:-e312f375-7442-4089-8022-ed232abc09e8}"
export RULE_TIMEOUT_SEC="${RULE_TIMEOUT_SEC:-420}"
export RULE_SYNC_WAIT_SEC="${RULE_SYNC_WAIT_SEC:-35}"
export PYTHONUNBUFFERED=1

echo "==> Demo manual checklist (Excès de vitesse)"
echo "    Org: $DEMO_ORG_ID"
echo "    UI: http://localhost:5174/demo"
echo "    MailHog: ${MAILHOG_PUBLIC_URL:-http://localhost:8025}"
echo ""

exec python3 "$ROOT/scripts/demo_manual_checklist.py"
