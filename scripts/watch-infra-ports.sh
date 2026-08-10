#!/usr/bin/env bash
# Keep Docker published ports alive (redis/mqtt/postgres/minio/ocr/mailhog).
# Catches "container running / host port dead" after Start-CiteVision.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
# shellcheck source=scripts/lib/service-heal.sh
source "$ROOT/scripts/lib/service-heal.sh"

LOGDIR="$ROOT/logs"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
INTERVAL="${WATCH_INFRA_INTERVAL:-30}"

mkdir -p "$LOGDIR"
echo "[watch-infra-ports] monitoring host publishes every ${INTERVAL}s"

while true; do
  if ! ensure_infra_host_ports >>"$LOGDIR/watch-infra-ports.log" 2>&1; then
    echo "[watch-infra-ports] heal incomplete at $(date -Is) — see logs/watch-infra-ports.log" >&2
  fi
  sleep "$INTERVAL"
done
