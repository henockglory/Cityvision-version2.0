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
  shared \
  docs/COMPOSITES-ORCHESTRATION.md \
  docs/CATALOG-VALIDATE-MATRIX.md \
  frontend/src/i18n \
  frontend/src/components/integrations \
  frontend/src/components/rules/OutputChannelsPanel.tsx \
  frontend/src/components/settings/AlertRoutingPanel.tsx \
  frontend/src/api/client.ts \
  backend/internal/routing \
  backend/internal/handler/integrations.go \
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
chmod +x "$DST/scripts/lib/probe-gemini.sh" "$DST/scripts/lib/set-gemini-key.sh" 2>/dev/null || true
sed -i 's/\r$//' \
  "$DST/scripts/lib/probe-gemini.sh" \
  "$DST/scripts/lib/set-gemini-key.sh" \
  "$DST/scripts/lib/start-full-stack.sh" \
  "$DST/scripts/lib/sync-runtime-no-env.sh" \
  "$DST/scripts/health_check_all.sh" 2>/dev/null || true
test -f "$DST/frontend/src/components/integrations/WebhookPayloadPreview.tsx"
test -f "$DST/backend/internal/handler/integrations.go"
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
    shared \
    docs/COMPOSITES-ORCHESTRATION.md \
    docs/CATALOG-VALIDATE-MATRIX.md \
    frontend/src/i18n \
    frontend/src/components/integrations \
    frontend/src/components/rules/OutputChannelsPanel.tsx \
    frontend/src/components/settings/AlertRoutingPanel.tsx \
    frontend/src/api/client.ts \
    backend/internal/routing \
    backend/internal/handler/integrations.go \
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
