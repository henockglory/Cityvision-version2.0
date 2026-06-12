#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test -f "$ROOT/ai-engine/src/citevision_ai/events/generator.py"
echo "[PASS] L8 Event generator module"
