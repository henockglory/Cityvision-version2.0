#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
set -a
# shellcheck disable=SC1091
source "$ENV_FILE"
set +a
[[ -n "${DATABASE_URL:-}" ]] || { echo "[FAIL] DATABASE_URL required"; exit 1; }
GO_BIN="/usr/local/go/bin/go"
[[ -x "$GO_BIN" ]] || GO_BIN="$(command -v go)"
echo "==> seed-demo-rules (ORG=${ORG_ID:-auto}, enabled=${DEMO_RULES_ENABLED:-1})"
"$GO_BIN" run ./cmd/seed-demo-rules
