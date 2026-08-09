#!/usr/bin/env bash
# One-shot start/restart of rules-engine. Continuous MQTT liveness is owned by
# scripts/watch-rules-engine.sh (started via start-full-stack when WATCH_RULES_ENGINE=1).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
LOGDIR="$ROOT/logs"
GO_BIN="/usr/local/go/bin/go"
[[ -x "$GO_BIN" ]] || GO_BIN="$(command -v go)"
stop_from_pid "$LOGDIR/rules-engine.pid" 2>/dev/null || true
# Also clear any stale binary process that may hold :8010 without the pid file.
pkill -f 'rules-engine/bin/rules-engine|cmd/rules-engine' 2>/dev/null || true
sleep 1
free_port "${RULES_ENGINE_PORT:-8010}"
# Prefer built binary when present (faster restart for watchdog).
if [[ -x "$ROOT/rules-engine/bin/rules-engine" ]]; then
  start_bg rules-engine "$ROOT/rules-engine" "$ROOT/rules-engine/bin/rules-engine" "$LOGDIR" "$ENV_FILE"
else
  start_bg rules-engine "$ROOT/rules-engine" "$GO_BIN run ./cmd/rules-engine" "$LOGDIR" "$ENV_FILE"
fi
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${RULES_ENGINE_PORT:-8010}/health" | python3 -m json.tool; then
    exit 0
  fi
  sleep 2
done
echo "[ERR] rules-engine health timeout"
exit 1
