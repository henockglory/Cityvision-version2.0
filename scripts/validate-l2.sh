#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for f in detection.json event.json rule.json; do
  test -f "$ROOT/shared/schemas/$f" || exit 1
  python3 -c "import json; json.load(open('$ROOT/shared/schemas/$f'))"
done
echo "[PASS] L2 schemas valid JSON"
