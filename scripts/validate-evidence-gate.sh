#!/usr/bin/env bash
# Unit checks for evidence completeness gate (Go) + icon assets present
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=== validate-evidence-gate ==="

echo ">>> go test evidence package"
(cd backend && go test ./internal/evidence/... -count=1)

echo ">>> icon assets"
test -f frontend/public/icons/presence.svg
test -f frontend/public/icons/quality.svg
test -f frontend/public/icons/rules/tpl-zone-enter.svg
UNDEF=$(grep -rl 'fill="undefined"' frontend/public/icons/rules 2>/dev/null | wc -l | tr -d ' ')
if [ "${UNDEF:-0}" != "0" ]; then
  echo "FAIL: $UNDEF rule icons still have fill=undefined"
  exit 1
fi
echo "PASS no fill=undefined in rule icons"

echo "=== validate-evidence-gate OK ==="
