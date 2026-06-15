#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
cd "$ROOT"
bash "$ROOT/scripts/restart-api-frontend.sh"
# rules-engine
source "$ROOT/scripts/lib/env-utils.sh"
bash "$ROOT/scripts/ensure-rules-sync-env.sh"
LOGDIR="$ROOT/logs"
ENV_FILE="$(ensure_env_file "$ROOT")"
stop_from_pid "$LOGDIR/rules-engine.pid" || true
free_port 8010 || true
sleep 1
start_bg rules-engine "$ROOT/rules-engine" "go run ./cmd/rules-engine" "$LOGDIR" "$ENV_FILE"
sleep 4
curl -sf "http://localhost:8010/health" && echo " [OK] rules-engine"
