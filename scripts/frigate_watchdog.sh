#!/usr/bin/env bash
# Keep Frigate API up, rebuild config when needed, ensure person track for face rules.
# Started by start-full-stack; also safe for cron.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
# shellcheck source=scripts/lib/service-heal.sh
source "$ROOT/scripts/lib/service-heal.sh"

ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

LOGDIR="$ROOT/logs"
mkdir -p "$LOGDIR"
INTERVAL="${WATCH_FRIGATE_INTERVAL:-45}"
LOOP="${WATCH_FRIGATE_LOOP:-0}"
FRIGATE_URL="${FRIGATE_URL:-http://127.0.0.1:5000}"
API="${BACKEND_API_URL:-http://127.0.0.1:8081/api/v1}"
KEY="${INTERNAL_API_KEY:-}"

heal_frigate_api() {
  if frigate_api_ok "${FRIGATE_URL}"; then
    return 0
  fi
  echo "[frigate-watchdog] API down — patient Frigate heal"
  if heal_frigate_host "${FRIGATE_HEAL_WAIT:-90}" "${FRIGATE_HEAL_RECREATE_WAIT:-120}"; then
    echo "[frigate-watchdog] Frigate API OK after heal"
    return 0
  fi
  echo "[frigate-watchdog] FAIL: Frigate API still unreachable" >&2
  return 1
}

rebuild_frigate_config() {
  if [[ "${FRIGATE_ENABLED:-0}" != "1" || "${FRIGATE_CONFIG_SYNC:-0}" != "1" ]]; then
    echo "[frigate-watchdog] rebuild skipped (FRIGATE_ENABLED/CONFIG_SYNC off)"
    return 0
  fi
  if [[ -z "$KEY" ]]; then
    echo "[frigate-watchdog] INTERNAL_API_KEY missing — skip rebuild" >&2
    return 1
  fi
  if ! curl -sf --max-time 3 "${API%/}/../health" >/dev/null 2>&1 \
    && ! curl -sf --max-time 3 "http://127.0.0.1:8081/health" >/dev/null 2>&1; then
    echo "[frigate-watchdog] backend down — skip rebuild"
    return 1
  fi
  local code
  code=$(curl -sS -o /tmp/frigate-rebuild.json -w "%{http_code}" --max-time 120 \
    -X POST -H "X-Internal-Key: $KEY" "$API/internal/ingest/frigate/rebuild" || echo "000")
  if [[ "$code" != "200" ]]; then
    echo "[frigate-watchdog] rebuild HTTP $code" >&2
    cat /tmp/frigate-rebuild.json 2>/dev/null || true
    return 1
  fi
  echo "[frigate-watchdog] rebuild OK"
  return 0
}

needs_person_track() {
  # True when active face watchlist entries or face_watchlist_match rules exist.
  docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
    "SELECT CASE WHEN EXISTS (
       SELECT 1 FROM surveillance_lists
       WHERE list_type='face_watchlist' AND is_active AND jsonb_array_length(entries)>0
     ) OR EXISTS (
       SELECT 1 FROM rules WHERE is_enabled
         AND (definition::text ILIKE '%face_watchlist_match%' OR definition::text ILIKE '%tpl-face-watchlist%')
     ) THEN 1 ELSE 0 END;" 2>/dev/null | tr -d '[:space:]' || echo 0
}

ensure_person_on_face_cameras() {
  local need
  need="$(needs_person_track)"
  if [[ "$need" != "1" ]]; then
    echo "[frigate-watchdog] no face rules/watchlist — person track check skipped"
    return 0
  fi
  if ! curl -sf --max-time 8 "${FRIGATE_URL%/}/api/config" -o /tmp/frigate-wd-cfg.json; then
    echo "[frigate-watchdog] config fetch failed"
    return 1
  fi
  local missing
  missing=$(python3 - <<'PY'
import json
c=json.load(open("/tmp/frigate-wd-cfg.json"))
cams=c.get("cameras") or {}
missing=[]
for fid, entry in cams.items():
  track=(entry.get("objects") or {}).get("track") or []
  if "person" not in track:
    missing.append(fid)
print(",".join(missing[:8]))
PY
)
  if [[ -z "$missing" ]]; then
    echo "[frigate-watchdog] person track OK on all cameras"
    return 0
  fi
  echo "[frigate-watchdog] person missing on: $missing — rebuild"
  rebuild_frigate_config || true
  sleep 5
  return 0
}

run_once() {
  echo "[frigate-watchdog] tick $(date -Is)"
  heal_frigate_api || return 1
  if [[ "${FRIGATE_ENABLED:-0}" == "1" && "${FRIGATE_CONFIG_SYNC:-0}" == "1" ]]; then
    # Light rebuild only when person track missing or forced
    ensure_person_on_face_cameras || true
  fi
}

# One-shot mode (cron / manual) when LOOP=0
if [[ "$LOOP" != "1" ]]; then
  run_once
  exit $?
fi

echo "[frigate-watchdog] loop every ${INTERVAL}s"
while true; do
  run_once >>"$LOGDIR/frigate-watchdog.log" 2>&1 || true
  sleep "$INTERVAL"
done
