#!/usr/bin/env bash
# Compute / compare frontend dist stamp so static UI rebuilds when WS/alerts sources change.
# Usage:
#   bash scripts/lib/frontend-dist-stamp.sh compute   → prints stamp
#   bash scripts/lib/frontend-dist-stamp.sh stale     → exit 0 if rebuild needed
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAMP_FILE="$ROOT/frontend/dist/.cv-dist-stamp"
SRCS=(
  "$ROOT/frontend/src/hooks/useAlertWebSocket.ts"
  "$ROOT/frontend/src/hooks/api/queries.ts"
  "$ROOT/frontend/src/pages/Alerts.tsx"
  "$ROOT/frontend/src/components/StackHealthGate.tsx"
  "$ROOT/scripts/serve-frontend-static.mjs"
  "$ROOT/frontend/index.html"
)

compute_stamp() {
  local f
  {
    for f in "${SRCS[@]}"; do
      if [[ -f "$f" ]]; then
        # content hash (mtime alone misses copy_one same-second writes)
        if command -v sha256sum >/dev/null 2>&1; then
          sha256sum "$f"
        else
          cksum "$f"
        fi
      else
        echo "MISSING $f"
      fi
    done
  } | sha256sum 2>/dev/null | awk '{print $1}'
}

cmd="${1:-compute}"
case "$cmd" in
  compute)
    compute_stamp
    ;;
  stale)
    want="$(compute_stamp)"
    have=""
    [[ -f "$STAMP_FILE" ]] && have="$(tr -d '[:space:]' < "$STAMP_FILE" || true)"
    if [[ ! -f "$ROOT/frontend/dist/index.html" ]]; then
      exit 0
    fi
    if [[ "$want" != "$have" ]]; then
      exit 0
    fi
    exit 1
    ;;
  write)
    mkdir -p "$ROOT/frontend/dist"
    compute_stamp > "$STAMP_FILE"
    ;;
  *)
    echo "usage: frontend-dist-stamp.sh compute|stale|write" >&2
    exit 2
    ;;
esac
