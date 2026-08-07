#!/usr/bin/env bash
# Test isolé 1-hit vitesse — Frigate-only (exit zone), hors moteur IA local.
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
export PATH="${ROOT}/ai-engine/.venv/bin:${PATH}"

# shellcheck source=scripts/microtest/_microtest_common.sh
source "$ROOT/scripts/microtest/_microtest_common.sh"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"

TS=$(microtest_ts)
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
REPORT="$LOG_DIR/1hit-vitesse-${TS}.md"
RUN_LOG="$LOG_DIR/1hit-vitesse-run-${TS}.log"
VALIDATE_LOG="$LOG_DIR/validate-vitesse-${TS}.log"
EXPORT_LOG="$LOG_DIR/export-vitesse-${TS}.log"

export HIT1_TS="$TS"
export RULE_ALIAS=vitesse
export RULE_NAME='Démo · Excès de vitesse'
export RULE_DURATION_SEC="${RULE_DURATION_SEC:-420}"
export POLL_SEC="${POLL_SEC:-8}"
export EVIDENCE_SETTLE_SEC="${EVIDENCE_SETTLE_SEC:-90}"
export FRIGATE_SPEED_BRIDGE=1
export FRIGATE_SPEED_EMIT_MODE=exit
export DEMO_ORG_ID="${DEMO_ORG_ID:-74d51ead-97a7-4e41-a488-503a9b90c466}"

ensure_demo_validation_env "$ROOT" "$ROOT/.env"
_upsert_env_kv_file "$ROOT/.env" FRIGATE_SPEED_BRIDGE 1
_upsert_env_kv_file "$ROOT/.env" FRIGATE_SPEED_EMIT_MODE exit

{
  echo "# 1-hit vitesse Frigate isolé — ${TS}"
  echo ""
  echo "Démarré: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo ""
  echo "Flags: FRIGATE_SPEED_BRIDGE=1 FRIGATE_SPEED_EMIT_MODE=exit (local ZoneSpeedEngine OFF)"
  echo ""
} > "$REPORT"

echo "=== 1-hit vitesse isolé TS=$TS ===" | tee "$RUN_LOG"

echo "=== preflight ===" | tee -a "$RUN_LOG"
PREFLIGHT_VALIDATE_LIGHT=1 bash "$ROOT/scripts/preflight-validate.sh" "$LOG_DIR/preflight-1hit-vitesse-${TS}.log" 2>&1 | tee -a "$RUN_LOG" || true

echo "=== restart AI (FRIGATE_SPEED_BRIDGE=1 EMIT=exit) ===" | tee -a "$RUN_LOG"
restart_ai 2>&1 | tee -a "$RUN_LOG" || { echo "[FAIL] AI restart" | tee -a "$REPORT"; exit 2; }

echo "=== ensure demo streams ===" | tee -a "$RUN_LOG"
bash "$ROOT/scripts/ensure-demo-streams.sh" 2>&1 | tee -a "$RUN_LOG" || true

# shellcheck source=scripts/lib/service-heal.sh
source "$ROOT/scripts/lib/service-heal.sh"
ensure_backend_up 30 2>&1 | tee -a "$RUN_LOG" || {
  bash "$ROOT/scripts/_restart_backend.sh" 2>&1 | tee -a "$RUN_LOG" || true
  ensure_backend_up 45 2>&1 | tee -a "$RUN_LOG" || {
    echo "[FAIL] backend not up" | tee -a "$REPORT"
    exit 2
  }
}
ensure_rules_engine_up 2>&1 | tee -a "$RUN_LOG" || true
curl -sf -X POST "http://127.0.0.1:${RULES_ENGINE_PORT:-8010}/internal/sync-rules" 2>&1 | tee -a "$RUN_LOG" || true

echo "=== patch vitesse limit → 1 km/h (rule binding + zone config, no geometry) ===" | tee -a "$RUN_LOG"
python3 -u "$ROOT/scripts/microtest/_patch_vitesse_1kmh.py" 2>&1 | tee -a "$RUN_LOG" || {
  echo "[FAIL] patch 1kmh" | tee -a "$REPORT"
  exit 2
}

# Force Frigate rebuild so speed_limit_kmh → speed_threshold is live
curl -sf -X POST -H "X-Internal-Key: ${INTERNAL_API_KEY:-changeme_internal_service_key}" \
  "http://127.0.0.1:8081/internal/frigate/rebuild" 2>&1 | tee -a "$RUN_LOG" || true

echo "=== wait Frigate API ===" | tee -a "$RUN_LOG"
FRIGATE_DEADLINE=$(( $(date +%s) + 90 ))
until curl -sf -m 5 "http://127.0.0.1:5000/api/version" >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$FRIGATE_DEADLINE" ]; then
    echo "[FAIL] Frigate API not ready" | tee -a "$RUN_LOG"
    exit 2
  fi
  docker start citevision-v2-frigate 2>/dev/null || true
  sleep 5
done

# Preflight: YAML must contain distances for at least one zone
if ! grep -qE 'distances:' "$ROOT/infra/frigate-config/config.yml" 2>/dev/null \
   && ! grep -qE 'distances:' "$ROOT/infra/frigate-config/frigate.generated.yml" 2>/dev/null; then
  echo "[WARN] no distances: in Frigate YAML — speed estimates may be missing" | tee -a "$RUN_LOG"
fi

HIT1_SINCE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export HIT1_SINCE
echo "HIT1_SINCE=$HIT1_SINCE" | tee -a "$RUN_LOG"

export RULE_NAME='Démo · Excès de vitesse'
export MAX_WAIT_SEC="$RULE_DURATION_SEC"
python3 -u "$ROOT/scripts/_validate_rule_frigate_1hit.py" 2>&1 | tee "$VALIDATE_LOG" | tee -a "$RUN_LOG" || true
VALIDATE_RC=${PIPESTATUS[0]:-1}
if grep -qE '^RESULT:.*PASS' "$VALIDATE_LOG" 2>/dev/null; then
  VALIDATE_RC=0
elif grep -q '^RESULT:' "$VALIDATE_LOG" 2>/dev/null; then
  VALIDATE_RC=1
fi

SINCE_FROM_LOG="$(grep -E '^HIT1_SINCE=' "$VALIDATE_LOG" 2>/dev/null | tail -1 | cut -d= -f2- || true)"
if [ -n "${SINCE_FROM_LOG:-}" ]; then
  export HIT1_SINCE="$SINCE_FROM_LOG"
fi

python3 -u "$ROOT/scripts/microtest/_export_1hit_vitesse_gallery.py" 2>&1 | tee "$EXPORT_LOG" | tee -a "$RUN_LOG" || true
EXPORT_RC=${PIPESTATUS[0]:-1}
if grep -q '^OVERALL_PASS=True' "$EXPORT_LOG" 2>/dev/null; then
  EXPORT_RC=0
elif grep -q '^OVERALL_PASS=' "$EXPORT_LOG" 2>/dev/null; then
  EXPORT_RC=1
fi

GALLERY_WSL="$ROOT/validation-evidence/1hit-vitesse-${TS}/index.html"
GALLERY_WIN="C:\\Users\\gheno\\citevision\\validation-evidence\\1hit-vitesse-${TS}\\index.html"

if [ "$VALIDATE_RC" -eq 0 ] && [ "$EXPORT_RC" -eq 0 ] && [ -f "$GALLERY_WSL" ]; then
  STATUS=PASS
else
  STATUS=FAIL
fi

{
  echo "## Résultat: ${STATUS}"
  echo ""
  echo "| Métrique | Valeur |"
  echo "|----------|--------|"
  echo "| validate_rc | ${VALIDATE_RC} |"
  echo "| export_rc | ${EXPORT_RC} |"
  echo "| HIT1_TS | ${TS} |"
  echo "| HIT1_SINCE | ${HIT1_SINCE:-?} |"
  echo "| FRIGATE_SPEED_BRIDGE | 1 |"
  echo "| FRIGATE_SPEED_EMIT_MODE | exit |"
  echo ""
  echo "## Galerie"
  echo "- WSL: \`validation-evidence/1hit-vitesse-${TS}/index.html\`"
  echo "- Windows: \`${GALLERY_WIN}\`"
} >> "$REPORT"

echo "=== RESULT: $STATUS ===" | tee -a "$RUN_LOG"
echo "GALLERY=$GALLERY_WSL" | tee -a "$RUN_LOG"
echo "Open: $GALLERY_WIN" | tee -a "$RUN_LOG"
[ "$STATUS" = "PASS" ] && exit 0
exit 1
