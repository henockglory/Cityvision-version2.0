#!/usr/bin/env bash
set -euo pipefail
WIN=/mnt/c/Users/gheno/citevision
DEST=~/citevision-v2

echo "=== Sync frontend/src -> WSL ==="
rsync -a --exclude node_modules --exclude dist "$WIN/frontend/src/" "$DEST/frontend/src/"
find "$DEST/frontend/src" -type f \( -name '*.ts' -o -name '*.tsx' -o -name '*.json' \) \
  -exec sed -i 's/\r$//' {} + 2>/dev/null || true

echo "=== Sync ai-engine evidence (capture preuves) ==="
rsync -a "$WIN/ai-engine/src/citevision_ai/evidence/" "$DEST/ai-engine/src/citevision_ai/evidence/"
find "$DEST/ai-engine/src/citevision_ai/evidence" -type f -name '*.py' \
  -exec sed -i 's/\r$//' {} + 2>/dev/null || true

grep -q imageRoles "$DEST/frontend/src/components/evidence/EvidencePolicyForm.tsx" \
  && echo "[OK] EvidencePolicyForm avec roles"
grep -q OBSERVATION_STRUCTURE_TEMPLATES "$DEST/frontend/src/lib/evidencePolicy.ts" \
  && echo "[OK] evidencePolicy.ts a jour"

echo "=== Restart frontend :5174 ==="
ROOT="$DEST"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
LOGDIR="$ROOT/logs"
stop_from_pid "$LOGDIR/frontend.pid" 2>/dev/null || true
pkill -f 'vite.*5174' 2>/dev/null || true
free_port 5174 5175 5176 5177 2>/dev/null || true
sleep 2
ENV_FILE="$(ensure_env_file "$ROOT")"
start_bg frontend "$ROOT/frontend" "npm run dev -- --host 0.0.0.0 --port 5174 --strictPort" "$LOGDIR" "$ENV_FILE"
if wait_http_ok "http://127.0.0.1:5174/" 90; then
  echo "[OK] Frontend http://localhost:5174"
else
  echo "[FAIL] Frontend non demarre"
  tail -25 "$LOGDIR/frontend.log" 2>/dev/null || true
  exit 1
fi
