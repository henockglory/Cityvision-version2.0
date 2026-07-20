#!/usr/bin/env bash
# Upsert demo E2E flags in WSL .env without wiping secrets.
set -euo pipefail
ENV="${1:-$HOME/citevision-v2/.env}"
test -f "$ENV" || { echo "[FAIL] missing $ENV"; exit 1; }
cp -n "$ENV" "$ENV.bak.pre-demo-e2e" 2>/dev/null || true

upsert() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV"; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV"
  else
    printf '%s=%s\n' "$key" "$val" >>"$ENV"
  fi
}

upsert DEMO_MODE 1
upsert DEMO_EVIDENCE_BACKEND strict_frigate
upsert DEMO_RESOLUTION 1080p
upsert LIVE_108_ENABLED 0

if grep -q '^EVIDENCE_BACKEND=frigate$' "$ENV"; then
  upsert EVIDENCE_BACKEND hybrid
elif ! grep -q '^EVIDENCE_BACKEND=' "$ENV"; then
  upsert EVIDENCE_BACKEND hybrid
fi

echo "--- demo flags ---"
grep -E '^(DEMO_MODE|DEMO_EVIDENCE_BACKEND|DEMO_RESOLUTION|LIVE_108_ENABLED|EVIDENCE_BACKEND)=' "$ENV"
