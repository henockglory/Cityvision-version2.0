#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test -f "$ROOT/ai-engine/src/citevision_ai/mqtt/publisher.py"
grep -q "cv/detections" "$ROOT/ai-engine/src/citevision_ai/mqtt/publisher.py"
echo "[PASS] L7 MQTT publisher"
