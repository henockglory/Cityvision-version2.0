#!/usr/bin/env bash
# Campagne PASS_1HIT — 5 règles démo séquentielles.
# Ordre: comptage(20) → vitesse(1km/h) → feu → ceinture → téléphone(pipeline Gemini)
set -uo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
export PATH="${ROOT}/ai-engine/.venv/bin:${PATH}"
export DEMO_ORG_ID="${DEMO_ORG_ID:-74d51ead-97a7-4e41-a488-503a9b90c466}"
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
REPORT="$LOG_DIR/demo5-report-${TS}.md"
CAMPAIGN_LOG="$LOG_DIR/demo5-campaign-${TS}.log"
HEAL_LOG="$LOG_DIR/demo5-heal-${TS}.log"
STEP_RETRY="${DEMO5_STEP_RETRY:-1}"
export DEMO5_CAMPAIGN_LOG="$CAMPAIGN_LOG"

source "$ROOT/scripts/microtest/_microtest_common.sh"
source "$ROOT/scripts/lib/env-utils.sh"

API="${BACKEND_API_URL:-http://127.0.0.1:8081}"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

append_result() {
  local step="$1" rule="$2" status="$3" detail="$4"
  echo "| $step | $rule | $status | $detail |" >> "$REPORT"
}

log_heal() {
  echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$HEAL_LOG" >> "$CAMPAIGN_LOG"
}

ensure_services_healthy() {
  # shellcheck source=scripts/lib/service-heal.sh
  source "$ROOT/scripts/lib/service-heal.sh"
  ensure_services_healthy || {
    curl -sf -m 5 "$API/health" >/dev/null || bash "$ROOT/scripts/_restart_backend.sh" 2>&1 | tee -a "$CAMPAIGN_LOG"
    ensure_services_healthy || true
  }
}

heal_step_failure() {
  local alias="$1"
  log_heal "HEAL start alias=$alias"
  case "$alias" in
    comptage)
      curl -sf -X POST -H "X-Internal-Key: $KEY" "$API/api/v1/internal/ingest/resync-spatial" || true
      curl -sf -X POST "http://127.0.0.1:8010/internal/sync-rules" || true
      sleep 30
      ;;
    vitesse|feu)
      bash "$ROOT/scripts/ensure-demo-streams.sh" 2>&1 | tee -a "$HEAL_LOG" || true
      curl -sf -X POST -H "X-Internal-Key: $KEY" "$API/api/v1/internal/demo/repair-streams" || true
      curl -sf -X POST -H "X-Internal-Key: $KEY" "$API/api/v1/internal/ingest/frigate/rebuild" || true
      sleep 15
      local nc
      nc=$(curl -sf http://127.0.0.1:5000/api/stats 2>/dev/null \
        | python3 -c "import sys,json; print(len((json.load(sys.stdin).get('cameras') or {})))" 2>/dev/null || echo 0)
      if [ "${nc:-0}" -lt 1 ]; then
        log_heal "HEAL frigate stats empty — docker restart frigate"
        docker restart citevision-v2-frigate >/dev/null 2>&1 || true
        sleep 25
        curl -sf -X POST -H "X-Internal-Key: $KEY" "$API/api/v1/internal/demo/repair-streams" || true
      fi
      curl -sf -X POST -H "X-Internal-Key: $KEY" "$API/api/v1/internal/ingest/resync-spatial" || true
      sleep 12
      ;;
    ceinture)
      bash "$ROOT/scripts/ensure-demo-streams.sh" 2>&1 | tee -a "$HEAL_LOG" || true
      curl -sf -X POST -H "X-Internal-Key: $KEY" "$API/api/v1/internal/demo/repair-streams" || true
      curl -sf -X POST -H "X-Internal-Key: $KEY" "$API/api/v1/internal/ingest/frigate/rebuild" || true
      python3 - <<PY
from pathlib import Path
p = Path("$ROOT/.env")
text = p.read_text(encoding="utf-8") if p.exists() else ""
tweaks = {"FRIGATE_CABIN_DEDUPE_SEC": "8", "GEMINI_MIN_INTERVAL_SEC": "3", "GEMINI_QUEUE_SIZE": "16"}
lines, seen = [], set()
for line in text.splitlines():
    if not line.strip() or "=" not in line or line.lstrip().startswith("#"):
        lines.append(line)
        continue
    k = line.split("=", 1)[0].strip()
    if k in tweaks:
        lines.append(f"{k}={tweaks[k]}")
        seen.add(k)
    else:
        lines.append(line)
for k, v in tweaks.items():
    if k not in seen:
        lines.append(f"{k}={v}")
p.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("ceinture_env_tweaks ok")
PY
      restart_ai || true
      sleep 15
      curl -sf -X POST -H "X-Internal-Key: $KEY" "$API/api/v1/internal/ingest/resync-spatial" || true
      sleep 12
      ;;
    telephone)
      if ! curl -sf -m 8 "$AI/health" | python3 -c "import json,sys; d=json.load(sys.stdin); exit(0 if str(d.get('gemini_configured','')).lower()=='true' else 1)"; then
        grep -q '^GEMINI_API_KEY=.' "$ROOT/.env" || ensure_gemini_key_from_preflight || true
        restart_ai || true
      fi
      curl -sf -X POST -H "X-Internal-Key: $KEY" "$API/api/v1/internal/ingest/resync-spatial" || true
      sleep 10
      ;;
  esac
  log_heal "HEAL done alias=$alias"
}

ensure_gemini_key_from_preflight() {
  bash "$ROOT/scripts/microtest/_microtest_demo5_preflight.sh" "$LOG_DIR/demo5-heal-preflight.log" 2>&1 | tail -5 || true
}

run_validate() {
  local step_log="$1"
  python3 -u "$ROOT/scripts/_validate_rule_frigate_1hit.py" 2>&1 | tee "$step_log" | tee -a "$CAMPAIGN_LOG"
  return "${PIPESTATUS[0]}"
}

run_step() {
  local step="$1" alias="$2" rule="$3" duration="$4"
  shift 4
  for kv in "$@"; do
    case "$kv" in
      *=*) export "$kv" ;;
    esac
  done
  export DEMO5_CURRENT_STEP="$step"
  export DEMO5_CURRENT_ALIAS="$alias"
  local step_log="$LOG_DIR/demo5-${alias}-${TS}.log"
  echo ""
  echo "=== [$step/5] $rule (max ${duration}s) ===" | tee -a "$CAMPAIGN_LOG"

  ensure_services_healthy
  sleep 2

  export RULE_NAME="$rule"
  export RULE_ALIAS="$alias"
  export RULE_DURATION_SEC="$duration"
  export OBSERVE_DURATION_SEC="$duration"
  export OBSERVE_OUT_DIR="$LOG_DIR"

  if [ "$alias" != "comptage" ]; then
    export FRIGATE_FRESH_MAX_AGE_SEC="${FRIGATE_FRESH_MAX_AGE_SEC:-120}"
    bash "$ROOT/scripts/ensure-demo-streams.sh" 2>&1 | tee -a "$CAMPAIGN_LOG" || true
    curl -sf -X POST -H "X-Internal-Key: $KEY" \
      "$API/api/v1/internal/ingest/resync-spatial" 2>&1 | tee -a "$CAMPAIGN_LOG" || true
    sleep 8
  fi

  python3 -u "$ROOT/scripts/_observe_1hit_blockers.py" > "$LOG_DIR/observe-${alias}-${TS}.out" 2>&1 &
  local obs_pid=$!

  set +e
  run_validate "$step_log"
  local rc=$?
  if [ "$rc" -ne 0 ] && [ "$STEP_RETRY" = "1" ]; then
    log_heal "STEP $step FAIL rc=$rc — auto-heal + retry"
    heal_step_failure "$alias"
    run_validate "$step_log.retry"
    rc=$?
  fi

  kill "$obs_pid" 2>/dev/null || true
  wait "$obs_pid" 2>/dev/null || true
  curl -sf -m 8 "$AI/debug/rule-blockers" > "$LOG_DIR/blockers-${alias}-final-${TS}.json" || true

  local status="FAIL"
  if [ "$rc" -eq 0 ]; then status="PASS"; fi
  local detail="rc=$rc log=$(basename "$step_log")"
  [ "$STEP_RETRY" = "1" ] && [ -f "${step_log}.retry" ] && detail="$detail retry=$(basename "${step_log}.retry")"
  append_result "$step" "$rule" "$status" "$detail"
  echo "STEP_RESULT step=$step alias=$alias status=$status rc=$rc" | tee -a "$CAMPAIGN_LOG"
  [ "$rc" -ne 0 ] && log_heal "STEP $step final FAIL alias=$alias"
  return "$rc"
}

{
  echo "# Demo 5 rules PASS_1HIT — $TS"
  echo ""
  echo "Level: PASS_1HIT pipeline (no DoD UI/MailHog)"
  echo ""
  echo "| Step | Rule | Status | Detail |"
  echo "|------|------|--------|--------|"
} > "$REPORT"

echo "=== Phase 0: preflight (blocking) ===" | tee "$CAMPAIGN_LOG"
bash "$ROOT/scripts/microtest/_microtest_demo5_preflight.sh" "$LOG_DIR/demo5-preflight-${TS}.log" \
  2>&1 | tee -a "$CAMPAIGN_LOG" || { echo "PREFLIGHT FAIL" | tee -a "$CAMPAIGN_LOG"; exit 2; }

FAIL=0
SPEED_PATCHED=0

run_step 1 comptage "Démo · Comptage véhicules" 1200 \
  COUNT_TARGET=20 POLL_SEC=10 || FAIL=1

if [ "$SPEED_PATCHED" = "0" ]; then
  echo "=== Phase 1b: speed zone 1 km/h (before step 2) ===" | tee -a "$CAMPAIGN_LOG"
  DEMO_SPEED_LIMIT_KMH=1 DEMO_ORG_ID="$DEMO_ORG_ID" bash "$ROOT/scripts/patch-demo-speed-zone.sh" \
    2>&1 | tee -a "$CAMPAIGN_LOG" || echo "WARN speed patch" | tee -a "$CAMPAIGN_LOG"
  curl -sf -X POST -H "X-Internal-Key: $KEY" "$API/api/v1/internal/ingest/resync-spatial" || true
  SPEED_PATCHED=1
fi

run_step 2 vitesse "Démo · Excès de vitesse" 600 \
  POLL_SEC=15 || FAIL=1

run_step 3 feu "Démo · Feu rouge" 720 \
  POLL_SEC=15 || FAIL=1

run_step 4 ceinture "Démo · Non-port ceinture" 720 \
  CEINTURE_PIPELINE_OR_ALERT=1 POLL_SEC=15 || FAIL=1

run_step 5 telephone "Démo · Téléphone au volant" 720 \
  VALIDATE_MODE=pipeline PHONE_PIPELINE_ONLY=1 POLL_SEC=12 || FAIL=1

PASS_COUNT=$(grep -c '| PASS |' "$REPORT" || true)
FRIGATE_CAMS=$(curl -sf http://127.0.0.1:5000/api/stats 2>/dev/null \
  | python3 -c "import sys,json; print(len((json.load(sys.stdin).get('cameras') or {})))" 2>/dev/null || echo "?")
GEMINI_OK=$(curl -sf -m 8 "$AI/health" 2>/dev/null \
  | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('gemini_configured','')).lower())" 2>/dev/null || echo "false")
{
  echo ""
  echo "## Summary"
  echo ""
  echo "- PASS: $PASS_COUNT / 5"
  echo "- Campaign log: \`$CAMPAIGN_LOG\`"
  echo "- Heal log: \`$HEAL_LOG\`"
  echo "- Overall: $([ "$FAIL" -eq 0 ] && echo PASS_1HIT || echo FAIL)"
  echo ""
  echo "## Blockers (if not 5/5)"
  echo ""
  echo "- \`gemini_configured\`: $GEMINI_OK"
  echo "- Frigate cameras in stats: $FRIGATE_CAMS"
  echo ""
  echo "## Auto-heal log"
  echo ""
  if [ -f "$HEAL_LOG" ]; then
    echo '```'
    tail -30 "$HEAL_LOG"
    echo '```'
  else
    echo "(none)"
  fi
} >> "$REPORT"

echo ""
echo "=== CAMPAIGN DONE pass=$PASS_COUNT/5 report=$REPORT ===" | tee -a "$CAMPAIGN_LOG"
export DEMO5_TS="$TS"
python3 "$ROOT/scripts/microtest/_demo5_export_evidence_html.py" 2>&1 | tee -a "$CAMPAIGN_LOG" || echo "WARN export html" | tee -a "$CAMPAIGN_LOG"
mkdir -p /mnt/c/Users/gheno/citevision/logs 2>/dev/null || true
cp "$REPORT" "$CAMPAIGN_LOG" "$HEAL_LOG" /mnt/c/Users/gheno/citevision/logs/ 2>/dev/null || true
cat "$REPORT"
exit "$FAIL"
