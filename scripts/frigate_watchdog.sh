#!/usr/bin/env bash
# Reconcile DB cameras/zones → Frigate generated config (watchdog / cron).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  # shellcheck source=scripts/lib/env-utils.sh
  source "$ROOT/scripts/lib/env-utils.sh"
  load_dotenv .env
fi

if [[ "${FRIGATE_ENABLED:-0}" != "1" || "${FRIGATE_CONFIG_SYNC:-0}" != "1" ]]; then
  echo "[frigate-watchdog] disabled (FRIGATE_ENABLED/FRIGATE_CONFIG_SYNC=0)"
  exit 0
fi

API="${BACKEND_API_URL:-http://127.0.0.1:8081/api/v1}"
KEY="${INTERNAL_API_KEY:-}"

if [[ -z "$KEY" ]]; then
  echo "[frigate-watchdog] INTERNAL_API_KEY missing" >&2
  exit 1
fi

echo "[frigate-watchdog] POST $API/internal/ingest/frigate/rebuild"
code=$(curl -sS -o /tmp/frigate-rebuild.json -w "%{http_code}" \
  -X POST -H "X-Internal-Key: $KEY" "$API/internal/ingest/frigate/rebuild" || echo "000")

if [[ "$code" != "200" ]]; then
  echo "[frigate-watchdog] rebuild failed HTTP $code" >&2
  cat /tmp/frigate-rebuild.json 2>/dev/null || true
  exit 1
fi

cat /tmp/frigate-rebuild.json
FRIGATE_URL="${FRIGATE_URL:-http://127.0.0.1:5000}"
if curl -sf "${FRIGATE_URL%/}/api/version" >/dev/null; then
  echo "[frigate-watchdog] Frigate API OK"
else
  echo "[frigate-watchdog] WARN: Frigate API unreachable at $FRIGATE_URL" >&2
fi
