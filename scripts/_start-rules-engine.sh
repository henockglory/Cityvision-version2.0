#!/usr/bin/env bash
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
free_port "${RULES_ENGINE_PORT:-8010}"
start_bg rules-engine "$ROOT/rules-engine" "$GO_BIN run ./cmd/rules-engine" "$LOGDIR" "$ENV_FILE"
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${RULES_ENGINE_PORT:-8010}/health" | python3 -m json.tool; then
    exit 0
  fi
  sleep 2
done
echo "[ERR] rules-engine health timeout"
exit 1
