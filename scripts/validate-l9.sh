#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for m in behavior state correlation; do
  test -f "$ROOT/ai-engine/src/citevision_ai/analytics/${m}.py"
done
echo "[PASS] L9 Analytics engines"
