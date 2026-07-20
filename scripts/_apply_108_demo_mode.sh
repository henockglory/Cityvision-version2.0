#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2

echo "=== sync key files ==="
for f in \
  backend/internal/frigate/sync.go \
  backend/internal/frigate/sync_test.go \
  ai-engine/src/citevision_ai/config.py \
  ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py \
  ai-engine/src/citevision_ai/main.py
do
  cp "/mnt/c/Users/gheno/citevision/$f" "$f"
  sed -i 's/\r$//' "$f"
  echo "ok $f"
done

echo "=== 108 in live frigate config ==="
grep -n '192.168.1.108' infra/frigate-config/config.yml || echo "not in config.yml"

echo "=== DEMO_MODE helpers in config.py ==="
grep -n 'demo_mode_source\|resolve_demo_mode\|demo_relaxed' ai-engine/src/citevision_ai/config.py | head -25

echo "=== skipFrigateHost in sync.go ==="
grep -n 'frigateExcludedHosts\|skipFrigateHost\|192.168.1.108' backend/internal/frigate/sync.go | head -20
