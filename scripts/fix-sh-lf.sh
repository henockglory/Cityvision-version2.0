#!/usr/bin/env bash
# Normalise tous les scripts shell en LF sans BOM (WSL/bash)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if command -v python3 >/dev/null 2>&1; then
  python3 "$ROOT/scripts/fix_crlf.py"
else
  find "$ROOT/scripts" -name '*.sh' -type f | while read -r f; do
    sed -i 's/\r$//' "$f" 2>/dev/null || sed -i '' 's/\r$//' "$f" 2>/dev/null || true
  done
fi
chmod +x "$ROOT"/scripts/*.sh "$ROOT"/scripts/e2e/lib/*.sh 2>/dev/null || true
echo "[OK] LF/BOM normalised for scripts/*.sh"
