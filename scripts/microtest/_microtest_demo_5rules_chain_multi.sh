#!/usr/bin/env bash
# Multi-hit chain smoke for 5 demo rules (NOT DoD).
# Targets: comptage x15, vitesse x3 distinct frigate_event, feu x1 Gemini,
# ceinture/telephone x3 Gemini cycles each (same pipeline path).
# Output: validation-evidence/chain-multi-<TS>/index.html + diagnostics.
set -uo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT" || exit 1
if [[ "$ROOT" == /mnt/* ]]; then
  echo "[FAIL] refuse /mnt runtime — cd ~/citevision-v2" >&2
  exit 1
fi

export PATH="${ROOT}/ai-engine/.venv/bin:${PATH}"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
# shellcheck source=scripts/microtest/_microtest_common.sh
source "$ROOT/scripts/microtest/_microtest_common.sh"

API="${BACKEND_API_URL:-http://127.0.0.1:8081}"
AI="${AI_URL:-http://127.0.0.1:8001}"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
CONTINUE_ON_FAIL="${CONTINUE_ON_FAIL:-1}"
POLL_SEC="${POLL_SEC:-8}"
RETENTION_MIN="${FRIGATE_DEMO_RETENTION_MIN:-5}"

resolve_org() {
  local org=""
  org="$(docker exec citevision-v2-postgres psql -U citevision -d citevision -tAc \
    "SELECT org_id::text FROM rules WHERE name LIKE 'Démo%' OR name LIKE 'Demo%' GROUP BY org_id ORDER BY COUNT(*) DESC LIMIT 1;" \
    2>/dev/null | tr -d '[:space:]' || true)"
  if [[ -z "$org" ]]; then
    org="$(docker exec citevision-v2-postgres psql -U citevision -d citevision -tAc \
      "SELECT org_id::text FROM org_demo_settings ORDER BY updated_at DESC NULLS LAST LIMIT 1;" \
      2>/dev/null | tr -d '[:space:]' || true)"
  fi
  if [[ -z "$org" ]]; then
    org="$(grep -E '^DEFAULT_ORG_ID=' "$ROOT/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d ' \r' || true)"
  fi
  if [[ -z "$org" ]]; then
    org="${DEMO_ORG_ID:-}"
  fi
  echo "$org"
}

DEMO_ORG_ID="$(resolve_org)"
if [[ -z "$DEMO_ORG_ID" ]]; then
  echo "[FAIL] cannot resolve DEMO_ORG_ID / DEFAULT_ORG_ID" >&2
  exit 2
fi
export DEMO_ORG_ID
export SKIP_UI_CAPTURE=1
export ADMIN_EMAIL="${ADMIN_EMAIL:-glory.henock@hologram.cd}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Hologram2026!}"
if [[ -n "$DEMO_ORG_ID" && -f "$ROOT/.env" ]]; then
  if grep -qE '^DEFAULT_ORG_ID=' "$ROOT/.env"; then
    sed -i "s/^DEFAULT_ORG_ID=.*/DEFAULT_ORG_ID=${DEMO_ORG_ID}/" "$ROOT/.env"
  else
    echo "DEFAULT_ORG_ID=${DEMO_ORG_ID}" >> "$ROOT/.env"
  fi
fi

TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
REPORT="$LOG_DIR/chain-multi-report-${TS}.md"
CAMPAIGN_LOG="$LOG_DIR/chain-multi-campaign-${TS}.log"
RESULTS_JSON="$LOG_DIR/chain-multi-results-${TS}.json"
export CHAIN_MULTI_TS="$TS"
export CHAIN_SMOKE_TS="$TS"
export CHAIN_MULTI_RESULTS_JSON="$RESULTS_JSON"
export CHAIN_SMOKE_RESULTS_JSON="$RESULTS_JSON"

purge_light() {
  echo "[purge] retention ${RETENTION_MIN}m" | tee -a "$CAMPAIGN_LOG"
  FRIGATE_DEMO_RETENTION_MIN="$RETENTION_MIN" bash "$ROOT/scripts/demo-retention-purge.sh" \
    2>&1 | tee -a "$CAMPAIGN_LOG" | tail -20 || true
}

disable_all_demo_rules() {
  docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
    "UPDATE rules SET is_enabled=false, updated_at=NOW() WHERE name LIKE 'Demo%' OR name LIKE 'Démo%';" \
    >/dev/null 2>&1 || true
}

append_result() {
  local step="$1" alias="$2" rule="$3" status="$4" detail="$5" elapsed="$6"
  echo "| $step | $alias | $rule | $status | ${elapsed}s | $detail |" >> "$REPORT"
  STEP_N="$step" STEP_ALIAS="$alias" STEP_RULE="$rule" STEP_STATUS="$status" \
  STEP_DETAIL="$detail" STEP_ELAPSED="$elapsed" STEP_LOG="chain-multi-${alias}-${TS}.log" \
  python3 - <<'PY'
import json, os
from pathlib import Path
p = Path(os.environ["CHAIN_MULTI_RESULTS_JSON"])
data = {"ts": os.environ.get("CHAIN_MULTI_TS",""), "org_id": os.environ.get("DEMO_ORG_ID",""), "campaign": "chain-multi", "steps": []}
if p.exists():
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
data.setdefault("steps", []).append({
    "step": int(os.environ.get("STEP_N") or 0),
    "alias": os.environ.get("STEP_ALIAS") or "",
    "rule": os.environ.get("STEP_RULE") or "",
    "status": os.environ.get("STEP_STATUS") or "",
    "elapsed_sec": int(os.environ.get("STEP_ELAPSED") or 0),
    "detail": os.environ.get("STEP_DETAIL") or "",
    "log": os.environ.get("STEP_LOG") or "",
})
p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
PY
}

ensure_services_healthy() {
  if [[ -f "$ROOT/scripts/lib/service-heal.sh" ]]; then
    # shellcheck source=scripts/lib/service-heal.sh
    source "$ROOT/scripts/lib/service-heal.sh"
    ensure_services_healthy || true
  fi
  curl -sf -m 5 "$API/health" >/dev/null 2>&1 || bash "$ROOT/scripts/_restart_backend.sh" >/dev/null 2>&1 || true
  if ! curl -sf -m 5 "$AI/health" >/dev/null 2>&1; then
    echo "[heal] AI down — _restart_ai_cuda.sh" | tee -a "$CAMPAIGN_LOG"
    if [[ -f "$ROOT/scripts/_restart_ai_cuda.sh" ]]; then
      bash "$ROOT/scripts/_restart_ai_cuda.sh" 2>&1 | tee -a "$CAMPAIGN_LOG" | tail -20 || true
    elif [[ -f "$ROOT/scripts/_restart_ai.py" ]]; then
      python3 "$ROOT/scripts/_restart_ai.py" 2>&1 | tee -a "$CAMPAIGN_LOG" | tail -20 || true
    fi
    for _i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
      curl -sf -m 5 "$AI/health" >/dev/null 2>&1 && break
      sleep 2
    done
  fi
}

run_validate() {
  local step_log="$1"
  python3 -u "$ROOT/scripts/_validate_rule_frigate_1hit.py" 2>&1 | tee "$step_log" | tee -a "$CAMPAIGN_LOG"
  return "${PIPESTATUS[0]}"
}

run_step() {
  local step="$1" alias="$2" rule="$3" duration="$4"
  shift 4
  unset VALIDATE_MODE PHONE_PIPELINE_ONLY CEINTURE_PIPELINE_OR_ALERT CEINTURE_PIPELINE_TARGET \
    PIPELINE_TARGET COUNT_TARGET ALERT_TARGET DISTINCT_SPEED || true
  for kv in "$@"; do
    case "$kv" in
      *=*) export "$kv" ;;
    esac
  done
  export RULE_NAME="$rule"
  export RULE_ALIAS="$alias"
  export RULE_DURATION_SEC="$duration"
  export OBSERVE_DURATION_SEC="$duration"
  export POLL_SEC
  local step_log="$LOG_DIR/chain-multi-${alias}-${TS}.log"
  local t0 t1 elapsed rc status detail
  t0="$(date +%s)"
  echo "" | tee -a "$CAMPAIGN_LOG"
  echo "=== [$step/5] $alias :: $rule (max ${duration}s) ===" | tee -a "$CAMPAIGN_LOG"

  ensure_services_healthy
  if [[ "$alias" != "comptage" ]]; then
    bash "$ROOT/scripts/ensure-demo-streams.sh" 2>&1 | tee -a "$CAMPAIGN_LOG" | tail -8 || true
    curl -sf -X POST -H "X-Internal-Key: $KEY" \
      "$API/api/v1/internal/ingest/resync-spatial" >/dev/null 2>&1 || true
    sleep 5
  fi

  set +e
  run_validate "$step_log"
  rc=$?
  set -e
  t1="$(date +%s)"
  elapsed=$((t1 - t0))
  status="FAIL"
  [[ "$rc" -eq 0 ]] && status="PASS"
  detail="rc=$rc"
  if grep -q '\[HIT\]' "$step_log" 2>/dev/null; then
    detail="$detail hit=$(grep -E '\[HIT\]' "$step_log" | tail -1 | tr -d '\r' | cut -c1-140)"
  elif grep -q '\[FAIL\]' "$step_log" 2>/dev/null; then
    detail="$detail fail=$(grep -E '\[FAIL\]' "$step_log" | tail -1 | tr -d '\r' | cut -c1-140)"
  fi
  append_result "$step" "$alias" "$rule" "$status" "$detail" "$elapsed"
  echo "STEP_RESULT step=$step alias=$alias status=$status elapsed=${elapsed}s rc=$rc" | tee -a "$CAMPAIGN_LOG"

  purge_light
  disable_all_demo_rules

  if [[ "$rc" -ne 0 ]]; then
    FAIL=1
    if [[ "$CONTINUE_ON_FAIL" != "1" ]]; then
      return "$rc"
    fi
  fi
  return 0
}

{
  echo "# Chain-multi 5 demo rules — $TS"
  echo ""
  echo "Level: multi-hit smoke (NOT DoD). Targets 15/3/1/3/3."
  echo "Org: \`$DEMO_ORG_ID\`"
  echo ""
  echo "| Step | Alias | Rule | Status | Elapsed | Detail |"
  echo "|------|-------|------|--------|---------|--------|"
} > "$REPORT"
echo "{}" > "$RESULTS_JSON"
: > "$CAMPAIGN_LOG"

echo "=== chain-multi START ts=$TS org=$DEMO_ORG_ID ===" | tee -a "$CAMPAIGN_LOG"

echo "=== Phase 0: purge + env + health ===" | tee -a "$CAMPAIGN_LOG"
purge_light
ensure_demo_runtime_env "$ROOT" "$ROOT/.env" 2>/dev/null || true
ensure_demo_validation_env "$ROOT" "$ROOT/.env" 2>/dev/null || true
bash "$ROOT/scripts/ensure-rules-sync-env.sh" --resolve-org 2>&1 | tee -a "$CAMPAIGN_LOG" | tail -10 || true
DEMO_ORG_ID="$(resolve_org)"
export DEMO_ORG_ID

if ! curl -sf -m 3 "http://127.0.0.1:1984/api" >/dev/null 2>&1; then
  echo "[heal] go2rtc API closed — compose recreate" | tee -a "$CAMPAIGN_LOG"
  if [[ -f "$ROOT/infra/docker-compose.yml" ]]; then
    (cd "$ROOT/infra" && docker compose up -d --force-recreate go2rtc) 2>&1 | tee -a "$CAMPAIGN_LOG" | tail -20 || true
    sleep 4
  fi
fi
bash "$ROOT/scripts/ensure-demo-streams.sh" 2>&1 | tee -a "$CAMPAIGN_LOG" | tail -20 || true
STREAM_N="$(curl -sf -m 5 http://127.0.0.1:1984/api/streams 2>/dev/null | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))' 2>/dev/null || echo 0)"
echo "go2rtc_streams=$STREAM_N" | tee -a "$CAMPAIGN_LOG"
if [[ "${STREAM_N:-0}" -lt 1 ]]; then
  echo "[FAIL] go2rtc has 0 streams after heal — abort" | tee -a "$CAMPAIGN_LOG"
  exit 2
fi

set +e
bash "$ROOT/scripts/health_check_all.sh" 2>&1 | tee "$LOG_DIR/chain-multi-health-${TS}.log" | tee -a "$CAMPAIGN_LOG" | tail -40
HEALTH_RC=${PIPESTATUS[0]}
set -e
echo "health_rc=$HEALTH_RC" | tee -a "$CAMPAIGN_LOG"
if ! curl -sf -m 5 "$API/health" >/dev/null 2>&1; then
  echo "[FAIL] API down after health — abort" | tee -a "$CAMPAIGN_LOG"
  exit 2
fi
if ! curl -sf -m 5 "$AI/health" >/dev/null 2>&1; then
  echo "[FAIL] AI down after health — abort (need GPU stack)" | tee -a "$CAMPAIGN_LOG"
  exit 2
fi
if ! curl -sf -m 5 "http://127.0.0.1:8010/health" >/dev/null 2>&1; then
  echo "[heal] rules-engine down — _start-rules-engine.sh" | tee -a "$CAMPAIGN_LOG"
  bash "$ROOT/scripts/_start-rules-engine.sh" 2>&1 | tee -a "$CAMPAIGN_LOG" | tail -15 || true
  sleep 3
fi
echo "resolved_DEMO_ORG_ID=$DEMO_ORG_ID" | tee -a "$CAMPAIGN_LOG"

FAIL=0

run_step 1 comptage "Démo · Comptage véhicules" 1200 \
  COUNT_TARGET=15 POLL_SEC=8 || FAIL=1

echo "=== speed zone patch 1 km/h ===" | tee -a "$CAMPAIGN_LOG"
DEMO_SPEED_LIMIT_KMH=1 DEMO_ORG_ID="$DEMO_ORG_ID" bash "$ROOT/scripts/patch-demo-speed-zone.sh" \
  2>&1 | tee -a "$CAMPAIGN_LOG" | tail -20 || echo "WARN speed patch" | tee -a "$CAMPAIGN_LOG"
curl -sf -X POST -H "X-Internal-Key: $KEY" "$API/api/v1/internal/ingest/resync-spatial" >/dev/null 2>&1 || true

run_step 2 vitesse "Démo · Excès de vitesse" 900 \
  ALERT_TARGET=3 DISTINCT_SPEED=1 POLL_SEC=8 || FAIL=1

run_step 3 feu "Démo · Feu rouge" 400 \
  VALIDATE_MODE=pipeline PIPELINE_TARGET=1 POLL_SEC=8 || FAIL=1

run_step 4 ceinture "Démo · Non-port ceinture" 900 \
  VALIDATE_MODE=pipeline PIPELINE_TARGET=3 POLL_SEC=8 || FAIL=1

run_step 5 telephone "Démo · Téléphone au volant" 900 \
  VALIDATE_MODE=pipeline PIPELINE_TARGET=3 POLL_SEC=8 || FAIL=1

PASS_COUNT="$(grep -c '| PASS |' "$REPORT" || true)"
{
  echo ""
  echo "## Summary"
  echo ""
  echo "- PASS: $PASS_COUNT / 5"
  echo "- Overall: $([ "$FAIL" -eq 0 ] && echo PASS_CHAIN_MULTI || echo FAIL_PARTIAL)"
  echo "- Targets: comptage=15, vitesse=3 distinct, feu=1, ceinture=3, telephone=3"
  echo "- Campaign log: \`$CAMPAIGN_LOG\`"
  echo "- Results JSON: \`$RESULTS_JSON\`"
} >> "$REPORT"

echo "=== final purge + disable demo rules ===" | tee -a "$CAMPAIGN_LOG"
disable_all_demo_rules
purge_light

export CHAIN_MULTI_TS="$TS"
export CHAIN_SMOKE_TS="$TS"
export CHAIN_MULTI_RESULTS_JSON="$RESULTS_JSON"
export CHAIN_SMOKE_RESULTS_JSON="$RESULTS_JSON"
python3 "$ROOT/scripts/microtest/_demo5_chain_multi_export_html.py" 2>&1 | tee -a "$CAMPAIGN_LOG" || echo "WARN export" | tee -a "$CAMPAIGN_LOG"

mkdir -p /mnt/c/Users/gheno/citevision/logs 2>/dev/null || true
cp -f "$REPORT" "$CAMPAIGN_LOG" "$RESULTS_JSON" /mnt/c/Users/gheno/citevision/logs/ 2>/dev/null || true

echo ""
echo "=== CHAIN-MULTI DONE pass=$PASS_COUNT/5 report=$REPORT ===" | tee -a "$CAMPAIGN_LOG"
cat "$REPORT"
exit "$FAIL"
