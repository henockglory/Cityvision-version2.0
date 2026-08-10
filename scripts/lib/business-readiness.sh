#!/usr/bin/env bash
# Business readiness — spatial AI / rules / Frigate zones / go2rtc streams.
# Sourced by start-full-stack, health_check_all, watch-business-readiness.
# Do NOT set -e/-o pipefail here: when sourced, pipefail breaks health_check pipelines.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  set -uo pipefail
fi

ROOT="${CITEVISION_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
API="${BACKEND_API_URL:-http://127.0.0.1:8081}"
AI="${AI_URL:-http://127.0.0.1:8001}"
RULES="${RULES_URL:-http://127.0.0.1:8010}"
GO2RTC="${GO2RTC_URL:-http://127.0.0.1:1984}"
FRIGATE="${FRIGATE_URL:-http://127.0.0.1:5000}"
PG_CONTAINER="${POSTGRES_CONTAINER:-citevision-v2-postgres}"

if ! declare -F load_dotenv >/dev/null 2>&1; then
  # shellcheck source=scripts/lib/env-utils.sh
  source "$ROOT/scripts/lib/env-utils.sh" 2>/dev/null || true
fi
if ! declare -F ensure_infra_host_ports >/dev/null 2>&1; then
  # shellcheck source=scripts/lib/service-heal.sh
  source "$ROOT/scripts/lib/service-heal.sh" 2>/dev/null || true
fi

_br_internal_key() {
  echo "${INTERNAL_API_KEY:-${KEY:-changeme_internal_service_key}}"
}

_br_api_port() {
  echo "${API_PORT:-8081}"
}

_br_post_internal() {
  local path="$1"
  local key
  key="$(_br_internal_key)"
  curl -sf --max-time 60 -X POST "http://127.0.0.1:$(_br_api_port)${path}" \
    -H "X-Internal-Key: $key" >/dev/null 2>&1
}

_br_psql() {
  local sql="$1"
  docker exec "$PG_CONTAINER" psql -U citevision -d citevision -At -F $'\t' -c "$sql" 2>/dev/null || true
}

# Active zones with a non-empty behavior: cam_id, zone_id, behavior (tab-separated).
_br_list_active_behavior_zones() {
  _br_psql "
SELECT c.id::text, z.id::text,
  COALESCE(NULLIF(z.behavior_config->>'behavior',''), NULLIF(z.zone_kind,''), '')
FROM zones z
JOIN cameras c ON c.id = z.camera_id
WHERE z.is_active = true
  AND z.camera_id IS NOT NULL
  AND (
    COALESCE(z.behavior_config->>'behavior','') <> ''
    OR COALESCE(z.zone_kind,'') <> ''
  )
ORDER BY c.id, z.id;
"
}

_br_enabled_rules_count() {
  _br_psql "SELECT COUNT(*)::text FROM rules WHERE is_enabled = true;" | head -1 | tr -d '[:space:]'
}

_br_stream_ready_cameras() {
  # cam_id \t go2rtc_src (may be empty → cam-<uuid>)
  _br_psql "
SELECT c.id::text,
  COALESCE(NULLIF(c.metadata->>'go2rtc_src',''), '')
FROM cameras c
WHERE COALESCE(c.metadata->>'stream_ready','') IN ('true','1')
   OR COALESCE(c.metadata->>'go2rtc_src','') <> ''
ORDER BY c.id;
"
}

heal_resync_spatial() {
  echo "[INFO] heal: POST /api/v1/internal/ingest/resync-spatial"
  _br_post_internal "/api/v1/internal/ingest/resync-spatial" || return 1
  sleep 2
  return 0
}

heal_frigate_rebuild() {
  echo "[INFO] heal: POST /api/v1/internal/ingest/frigate/rebuild"
  _br_post_internal "/api/v1/internal/ingest/frigate/rebuild" || return 1
  local i
  for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    if curl -sf --max-time 5 "$FRIGATE/api/version" >/dev/null 2>&1; then
      sleep 2
      return 0
    fi
    sleep 2
  done
  return 1
}

heal_repair_streams() {
  echo "[INFO] heal: repair-streams + ensure-demo-streams"
  _br_post_internal "/api/v1/internal/demo/repair-streams" || true
  if [[ -f "$ROOT/scripts/ensure-demo-streams.sh" ]]; then
    bash "$ROOT/scripts/ensure-demo-streams.sh" >/dev/null 2>&1 || true
  fi
  if declare -F heal_published_container >/dev/null 2>&1; then
    if ! curl -sf --max-time 3 "$GO2RTC/api" >/dev/null 2>&1; then
      heal_published_container citevision-v2-go2rtc go2rtc 1984 8554 8555 || true
    fi
  fi
  sleep 2
  return 0
}

heal_rules_engine() {
  echo "[INFO] heal: rules-engine restart + resync-spatial"
  if [[ -f "$ROOT/scripts/_start-rules-engine.sh" ]]; then
    bash "$ROOT/scripts/_start-rules-engine.sh" >/dev/null 2>&1 || true
  fi
  heal_resync_spatial || true
  sleep 3
  return 0
}

# Returns 0 if AI spatial matches DB for every camera that has active behavior zones.
probe_spatial_ai_hot() {
  local rows
  rows="$(_br_list_active_behavior_zones)"
  if [[ -z "$(echo "$rows" | tr -d '[:space:]')" ]]; then
    echo "[OK] spatial AI: no active behavior zones in DB (nothing to guarantee)"
    return 0
  fi
  printf '%s\n' "$rows" | AI_URL="$AI" python3 -c '
import json, os, sys, collections, urllib.request
ai = os.environ.get("AI_URL", "http://127.0.0.1:8001").rstrip("/")
rows = [ln.split("\t") for ln in sys.stdin.read().splitlines() if ln.strip()]
by = collections.defaultdict(list)
for r in rows:
    if len(r) < 3:
        continue
    cam, zid, beh = r[0].strip(), r[1].strip(), r[2].strip()
    by[cam].append((zid, beh))
fail = 0
for cam, zones in by.items():
    expect_n = len(zones)
    expect_beh = {b for _, b in zones if b}
    try:
        with urllib.request.urlopen(f"{ai}/cameras/{cam}/spatial", timeout=8) as resp:
            d = json.load(resp)
    except Exception as e:
        print(f"[FAIL] spatial AI camera={cam[:8]} unreachable: {e}")
        fail = 1
        continue
    zc = int(d.get("zone_count") or 0)
    behaviors = {str(b) for b in (d.get("behaviors") or []) if str(b).strip()}
    if zc < 1:
        print(f"[FAIL] spatial AI camera={cam[:8]} zone_count=0 (db_zones={expect_n})")
        fail = 1
        continue
    if expect_beh and not (expect_beh & behaviors):
        print(f"[FAIL] spatial AI camera={cam[:8]} behaviors={sorted(behaviors)} missing any of {sorted(expect_beh)}")
        fail = 1
        continue
    print(f"[OK] spatial AI camera={cam[:8]} zone_count={zc} behaviors={sorted(behaviors)}")
sys.exit(fail)
'
}

ensure_spatial_ai_hot() {
  if probe_spatial_ai_hot; then
    return 0
  fi
  echo "[WARN] spatial AI cold — heal resync-spatial (x3)"
  local i
  for i in 1 2 3; do
    heal_resync_spatial || true
    sleep 2
    if probe_spatial_ai_hot; then
      echo "[OK] spatial AI hot after heal attempt $i"
      return 0
    fi
  done
  echo "[FAIL] spatial AI still cold after resync-spatial"
  return 1
}

probe_rules_parity() {
  local db_n ar
  db_n="$(_br_enabled_rules_count)"
  db_n="${db_n:-0}"
  if [[ "$db_n" =~ ^[0-9]+$ ]] && [[ "$db_n" -eq 0 ]]; then
    echo "[OK] rules parity: no enabled rules in DB"
    return 0
  fi
  ar="$(curl -sf --max-time 5 "$RULES/health" 2>/dev/null | python3 -c 'import sys,json; print(int(json.load(sys.stdin).get("active_rules") or 0))' 2>/dev/null || echo 0)"
  if [[ "$ar" =~ ^[0-9]+$ ]] && [[ "$ar" -ge 1 ]]; then
    echo "[OK] rules parity: db_enabled=$db_n active_rules=$ar"
    return 0
  fi
  echo "[FAIL] rules parity: db_enabled=$db_n active_rules=${ar:-0}"
  return 1
}

ensure_rules_parity() {
  if probe_rules_parity; then
    return 0
  fi
  echo "[WARN] rules cold — heal rules-engine"
  heal_rules_engine
  if probe_rules_parity; then
    echo "[OK] rules parity after heal"
    return 0
  fi
  echo "[FAIL] rules parity still broken after heal"
  return 1
}

probe_frigate_zones() {
  local rows
  rows="$(_br_list_active_behavior_zones)"
  if [[ -z "$(echo "$rows" | tr -d '[:space:]')" ]]; then
    echo "[OK] Frigate zones: no active behavior zones in DB"
    return 0
  fi
  printf '%s\n' "$rows" | FRIGATE_URL="$FRIGATE" python3 -c '
import json, os, sys, urllib.request, collections
fr = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000").rstrip("/")
rows = [ln.split("\t") for ln in sys.stdin.read().splitlines() if ln.strip()]
by = collections.defaultdict(list)
for r in rows:
    if len(r) < 2:
        continue
    cam, zid = r[0].strip(), r[1].strip()
    by[cam].append(zid)
try:
    with urllib.request.urlopen(f"{fr}/api/config", timeout=10) as resp:
        cfg = json.load(resp)
except Exception as e:
    print(f"[FAIL] Frigate /api/config unreachable: {e}")
    raise SystemExit(1)
cams = cfg.get("cameras") or {}
fail = 0
checked = 0
for cam, zids in by.items():
    fk = f"cv_{cam}"
    if fk not in cams:
        # Camera may not be in Frigate yet — fail for cams that have zones
        print(f"[FAIL] Frigate missing camera {fk}")
        fail = 1
        continue
    zones = (cams[fk] or {}).get("zones") or {}
    for zid in zids:
        zk = f"cv_zone_{zid}"
        checked += 1
        if zk not in zones:
            print(f"[FAIL] Frigate missing zone {zk} on {fk}")
            fail = 1
        else:
            print(f"[OK] Frigate zone {zk[:24]}… on {fk[:20]}…")
if checked == 0:
    print("[OK] Frigate zones: nothing to check")
sys.exit(fail)
'
}

ensure_frigate_zones() {
  if probe_frigate_zones; then
    return 0
  fi
  echo "[WARN] Frigate zones mismatch — rebuild"
  heal_frigate_rebuild || true
  sleep 3
  if probe_frigate_zones; then
    echo "[OK] Frigate zones after rebuild"
    return 0
  fi
  echo "[FAIL] Frigate zones still mismatched after rebuild"
  return 1
}

probe_go2rtc_streams() {
  local rows
  rows="$(_br_stream_ready_cameras)"
  if [[ -z "$(echo "$rows" | tr -d '[:space:]')" ]]; then
    echo "[OK] go2rtc streams: no stream_ready cameras in DB"
    return 0
  fi
  printf '%s\n' "$rows" | GO2RTC_URL="$GO2RTC" python3 -c '
import json, os, sys, urllib.request
g2 = os.environ.get("GO2RTC_URL", "http://127.0.0.1:1984").rstrip("/")
rows = [ln.split("\t") for ln in sys.stdin.read().splitlines() if ln.strip()]
try:
    with urllib.request.urlopen(f"{g2}/api/streams", timeout=8) as resp:
        streams = json.load(resp)
except Exception as e:
    print(f"[FAIL] go2rtc /api/streams unreachable: {e}")
    raise SystemExit(1)
if not isinstance(streams, dict):
    print("[FAIL] go2rtc streams payload not a dict")
    raise SystemExit(1)
fail = 0
for r in rows:
    cam = r[0].strip()
    src = (r[1].strip() if len(r) > 1 else "") or f"cam-{cam}"
    if src not in streams:
        print(f"[FAIL] go2rtc missing stream src={src}")
        fail = 1
    else:
        print(f"[OK] go2rtc stream {src[:40]}")
sys.exit(fail)
'
}

ensure_go2rtc_streams() {
  if probe_go2rtc_streams; then
    return 0
  fi
  echo "[WARN] go2rtc streams missing — repair"
  heal_repair_streams
  if probe_go2rtc_streams; then
    echo "[OK] go2rtc streams after repair"
    return 0
  fi
  echo "[FAIL] go2rtc streams still missing after repair"
  return 1
}

# Main entry: probe+heal all business readiness checks.
# Returns 0 on success. Under STRICT_INSTALL_HEALTH=1 callers should abort Start on failure.
# soft=1 (watchdog): still heals, returns 1 on failure but message is WARN-oriented.
ensure_business_readiness() {
  local soft="${1:-0}"
  local rc=0
  echo "=== business readiness ==="

  if ! ensure_spatial_ai_hot; then
    rc=1
  fi
  if ! ensure_rules_parity; then
    rc=1
  fi
  if ! ensure_frigate_zones; then
    rc=1
  fi
  if ! ensure_go2rtc_streams; then
    rc=1
  fi

  if [[ "$rc" -eq 0 ]]; then
    echo "[OK] business readiness"
  else
    if [[ "$soft" == "1" ]]; then
      echo "[WARN] business readiness incomplete after heal"
    else
      echo "[FAIL] business readiness incomplete after heal"
    fi
  fi
  return "$rc"
}
