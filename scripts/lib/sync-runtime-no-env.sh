#!/usr/bin/env bash
# Sync plan-critical paths Windows -> WSL + mirrors; never overwrite .env.
set -euo pipefail
SRC="${1:-/mnt/c/Users/gheno/citevision}"
DST="${2:-$HOME/citevision-v2}"

sync_tree() {
  local from="$1" to="$2"
  mkdir -p "$to"
  rsync -a --no-owner --no-group --no-perms \
    --exclude '.git/' \
    --exclude '.env' \
    --exclude 'frontend/.env' \
    --exclude 'infra/.env' \
    --exclude 'node_modules/' \
    --exclude 'frontend/node_modules/' \
    --exclude 'ai-engine/.venv/' \
    --exclude '.venv/' \
    --exclude 'logs/' \
    --exclude 'validation-evidence/' \
    --exclude 'backend/bin/' \
    --exclude 'rules-engine/bin/' \
    --exclude 'infra/' \
    --exclude 'data/' \
    --exclude 'vendor/citevision_videoverbalisation/' \
    "$from/" "$to/" || true
}

echo "=== sync critical paths $SRC -> $DST ==="
mkdir -p "$DST"
for rel in \
  launcher \
  scripts/lib \
  scripts/health_check_all.sh \
  scripts/watch-infra-ports.sh \
  scripts/watch-business-readiness.sh \
  scripts/watch-backend.sh \
  scripts/validate_demo_1hit_seven_reactive.py \
  scripts/_p7_reactive.sh \
  scripts/stop-linux.sh \
  shared \
  docs/COMPOSITES-ORCHESTRATION.md \
  docs/CATALOG-VALIDATE-MATRIX.md \
  frontend/src/i18n \
  frontend/src/config/streams.ts \
  frontend/src/pages/Login.tsx \
  frontend/src/components/live/FrigateLivePlayer.tsx \
  frontend/src/components/live/LiveStreamPlayer.tsx \
  frontend/src/components/demo/DemoVideoPanel.tsx \
  scripts/lib/sync-live-preview-ui.sh \
  scripts/lib/business-readiness.sh \
  frontend/src/components/integrations \
  frontend/src/components/rules/OutputChannelsPanel.tsx \
  frontend/src/components/settings/AlertRoutingPanel.tsx \
  frontend/src/api/client.ts \
  backend/internal/routing \
  backend/internal/auth \
  backend/internal/handler \
  backend/internal/frigate \
  backend/internal/demo \
  backend/internal/ingest \
  backend/cmd/api/main.go
do
  if [[ -d "$SRC/$rel" ]]; then
    mkdir -p "$DST/$rel"
    rsync -a --no-owner --no-group --no-perms "$SRC/$rel/" "$DST/$rel/"
  elif [[ -f "$SRC/$rel" ]]; then
    mkdir -p "$(dirname "$DST/$rel")"
    rsync -a --no-owner --no-group --no-perms "$SRC/$rel" "$DST/$rel"
  else
    echo "skip missing $rel"
  fi
done
chmod +x \
  "$DST/scripts/lib/probe-gemini.sh" \
  "$DST/scripts/lib/set-gemini-key.sh" \
  "$DST/scripts/lib/service-heal.sh" \
  "$DST/scripts/lib/business-readiness.sh" \
  "$DST/scripts/watch-infra-ports.sh" \
  "$DST/scripts/watch-business-readiness.sh" \
  "$DST/scripts/health_check_all.sh" \
  "$DST/scripts/stop-linux.sh" 2>/dev/null || true
sed -i 's/\r$//' \
  "$DST/scripts/lib/probe-gemini.sh" \
  "$DST/scripts/lib/set-gemini-key.sh" \
  "$DST/scripts/lib/service-heal.sh" \
  "$DST/scripts/lib/business-readiness.sh" \
  "$DST/scripts/lib/start-full-stack.sh" \
  "$DST/scripts/lib/sync-runtime-no-env.sh" \
  "$DST/scripts/watch-infra-ports.sh" \
  "$DST/scripts/watch-business-readiness.sh" \
  "$DST/scripts/health_check_all.sh" \
  "$DST/scripts/stop-linux.sh" 2>/dev/null || true
test -f "$DST/scripts/watch-infra-ports.sh"
test -f "$DST/scripts/watch-business-readiness.sh"
test -f "$DST/scripts/lib/service-heal.sh"
test -f "$DST/scripts/lib/business-readiness.sh"
grep -q 'ensure_infra_host_ports' "$DST/scripts/lib/service-heal.sh"
grep -q 'ensure_business_readiness' "$DST/scripts/lib/business-readiness.sh"
grep -q 'ErrSessionStore' "$DST/backend/internal/auth/service.go"
if grep -q 'tpl-theft-composite' "$DST/shared/rule-orchestration-contract.json" 2>/dev/null; then
  echo "[FAIL] theft composite still present in WSL orchestration" >&2
  exit 1
fi
echo "WSL_OK"

for m in \
  /mnt/c/Users/gheno/citevision-v2 \
  /mnt/c/Users/gheno/citevision_optimized \
  /mnt/c/Citevision
do
  [[ -d "$m" ]] || { echo "skip missing $m"; continue; }
  echo "=== mirror -> $m ==="
  for rel in \
    launcher \
    scripts/lib \
    scripts/health_check_all.sh \
    scripts/watch-infra-ports.sh \
    scripts/watch-business-readiness.sh \
    scripts/watch-backend.sh \
    scripts/validate_demo_1hit_seven_reactive.py \
    scripts/_p7_reactive.sh \
    scripts/stop-linux.sh \
    shared \
    docs/COMPOSITES-ORCHESTRATION.md \
    docs/CATALOG-VALIDATE-MATRIX.md \
    frontend/src/i18n \
    frontend/src/config/streams.ts \
    frontend/src/pages/Login.tsx \
    frontend/src/components/live/FrigateLivePlayer.tsx \
    frontend/src/components/live/LiveStreamPlayer.tsx \
    frontend/src/components/demo/DemoVideoPanel.tsx \
    frontend/src/components/integrations \
    frontend/src/components/rules/OutputChannelsPanel.tsx \
    frontend/src/components/settings/AlertRoutingPanel.tsx \
    frontend/src/api/client.ts \
    backend/internal/routing \
    backend/internal/auth \
    backend/internal/handler \
    backend/internal/frigate \
    backend/internal/demo \
    backend/internal/ingest \
    backend/cmd/api/main.go
  do
    if [[ -d "$DST/$rel" ]]; then
      mkdir -p "$m/$rel"
      rsync -a --no-owner --no-group --no-perms "$DST/$rel/" "$m/$rel/"
    elif [[ -f "$DST/$rel" ]]; then
      mkdir -p "$(dirname "$m/$rel")"
      rsync -a --no-owner --no-group --no-perms "$DST/$rel" "$m/$rel"
    fi
  done
  echo "OK $m"
done
echo ALL_SYNC_OK
