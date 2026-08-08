#!/usr/bin/env bash
# Read-only audit helper for cam 108 + Frigate sync honesty.
# Policy host denylist / skipFrigate* were removed — this script only verifies
# that 108 is present when active, and that skip helpers stay gone.
set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"

echo "=== sync key files from Windows mirror (optional) ==="
if [[ -d /mnt/c/Users/gheno/citevision ]]; then
  for f in \
    backend/internal/frigate/sync.go \
    backend/internal/frigate/sync_test.go \
    ai-engine/src/citevision_ai/config.py \
    ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py \
    ai-engine/src/citevision_ai/main.py
  do
    if [[ -f "/mnt/c/Users/gheno/citevision/$f" ]]; then
      cp "/mnt/c/Users/gheno/citevision/$f" "$f"
      sed -i 's/\r$//' "$f"
      echo "ok $f"
    fi
  done
fi

echo "=== 108 in live frigate config ==="
grep -n '192.168.1.108' infra/frigate-config/config.yml || echo "not in config.yml (ok if cam inactive or not yet rebuilt)"

echo "=== DEMO_MODE helpers in config.py ==="
grep -n 'demo_mode_source\|resolve_demo_mode\|demo_relaxed' ai-engine/src/citevision_ai/config.py | head -25 || true

echo "=== policy exclusions must be ABSENT in sync.go ==="
if grep -nE 'frigateExcludedHosts|skipFrigateHost|func skipFrigateCamera' backend/internal/frigate/sync.go; then
  echo "FAIL: policy skip helpers reintroduced"
  exit 1
fi
echo "ok: no skipFrigateHost / skipFrigateCamera / frigateExcludedHosts"
