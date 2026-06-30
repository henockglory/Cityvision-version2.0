#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2
bash scripts/sync-all-targets.sh 2>&1 | tail -2
sed -i 's/\r$//' scripts/*.sh scripts/*.py ai-engine/scripts/*.py 2>/dev/null || true
bash scripts/restart-ai-ingest.sh 2>&1 | tail -20
echo "=== Spatial audit ==="
bash scripts/inspect-demo-spatial.sh 2>&1 | tail -15
