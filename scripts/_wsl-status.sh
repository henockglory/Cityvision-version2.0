#!/usr/bin/env bash
set -euo pipefail
echo "=== Health ==="
curl -sf http://localhost:8081/health && echo
curl -sf http://localhost:8001/health | python3 -m json.tool 2>/dev/null || echo "AI down"
curl -sf http://localhost:8010/health && echo
echo "=== Secondary models ==="
ls -la ~/citevision-v2/ai-engine/models/secondary/*.onnx 2>/dev/null || echo "none"
echo "=== AI cameras ==="
curl -sf http://localhost:8001/cameras 2>/dev/null | python3 -m json.tool 2>/dev/null | head -40 || echo "no cameras endpoint"
