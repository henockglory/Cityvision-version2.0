#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for doc in STATE DECISIONS ARCHITECTURE PORTS INSTALL OPERATIONS; do
  test -f "$ROOT/docs/${doc}.md"
done
echo "[PASS] L13 Documentation"
