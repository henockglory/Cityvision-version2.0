#!/usr/bin/env bash
# Wrapper — toute la logique est dans _validate_3rules_1hit.py
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec python3 -u scripts/_validate_3rules_1hit.py
