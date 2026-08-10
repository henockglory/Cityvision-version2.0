#!/usr/bin/env bash
# Keep business readiness hot (spatial AI / rules / Frigate zones / go2rtc streams).
# Catches "services UP / spatial cold" after Start-CiteVision.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
# shellcheck source=scripts/lib/service-heal.sh
source "$ROOT/scripts/lib/service-heal.sh"
# shellcheck source=scripts/lib/business-readiness.sh
source "$ROOT/scripts/lib/business-readiness.sh"

LOGDIR="$ROOT/logs"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
INTERVAL="${WATCH_BUSINESS_INTERVAL:-30}"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
export KEY INTERNAL_API_KEY="$KEY"

mkdir -p "$LOGDIR"
echo "[watch-business-readiness] monitoring every ${INTERVAL}s"

while true; do
  if ! ensure_business_readiness 1 >>"$LOGDIR/watch-business-readiness.log" 2>&1; then
    echo "[watch-business-readiness] incomplete at $(date -Is) — see logs/watch-business-readiness.log" >&2
  fi
  sleep "$INTERVAL"
done
