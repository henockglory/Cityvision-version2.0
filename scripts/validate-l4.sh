#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test -f "$ROOT/ai-engine/pyproject.toml"
test -f "$ROOT/ai-engine/requirements.txt"
test -f "$ROOT/ai-engine/Dockerfile"
echo "[PASS] L4 AI engine packaging"
