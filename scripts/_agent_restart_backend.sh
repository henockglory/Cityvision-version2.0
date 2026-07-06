#!/usr/bin/env bash
set -euo pipefail
ROOT="${HOME}/citevision-v2"
cd "$ROOT"
export PATH="${PATH}:/usr/local/go/bin"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
LOGDIR="$ROOT/logs"
stop_from_pid "$LOGDIR/backend.pid" || true
free_port 8081 || true
sleep 1
start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
for _ in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8081/health >/dev/null 2>&1; then
    echo "backend OK"
    exit 0
  fi
  sleep 1
done
echo "backend FAIL"
tail -8 "$LOGDIR/backend.log"
exit 1
