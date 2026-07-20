#!/usr/bin/env bash
# Morning resume: stack-up + Vite + sync validation scripts + cabin types check
set -uo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cd "$ROOT"
export PATH="/usr/local/go/bin:$HOME/go/bin:$PATH"

# Sync critical fixes from Windows edit tree
for f in \
  scripts/stack-up.sh \
  scripts/validate_rule_dod.py \
  scripts/_validate_rule_frigate_1hit.py \
  scripts/capture_alerts_ui.mjs \
  ai-engine/src/citevision_ai/evidence/service.py \
  backend/internal/evidence/completeness.go
do
  if [[ -f "$WIN/$f" ]]; then
    mkdir -p "$(dirname "$ROOT/$f")"
    cp -f "$WIN/$f" "$ROOT/$f"
    sed -i 's/\r$//' "$ROOT/$f"
  fi
done

# VIDEOS_PATH must be WSL-native
if grep -q 'VIDEOS_PATH=/mnt/c/' "$ROOT/.env" 2>/dev/null; then
  sed -i 's|^VIDEOS_PATH=.*|VIDEOS_PATH=/home/gheno/citevision-v2/data/videos|' "$ROOT/.env"
fi

bash "$ROOT/scripts/stack-up.sh" || true

# Vite
if ! curl -sf --max-time 2 http://127.0.0.1:5174/ >/dev/null; then
  cd "$ROOT/frontend"
  nohup npm run dev -- --host 127.0.0.1 --port 5174 > /tmp/citevision-vite.log 2>&1 &
  for i in $(seq 1 30); do
    curl -sf --max-time 2 http://127.0.0.1:5174/ >/dev/null && break
    sleep 1
  done
fi

# Confirm cabin types include phone_driving
"$ROOT/ai-engine/.venv/bin/python" -c \
  'from citevision_ai.evidence.service import EvidenceCaptureService as S; print(sorted(S._CABIN_EVENT_TYPES))' \
  || true

bash "$ROOT/scripts/health_check_all.sh" || true
echo "=== boot done $(date -Is) ==="
