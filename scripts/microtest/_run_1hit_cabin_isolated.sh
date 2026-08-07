#!/usr/bin/env bash
# Test isolé cabine (ceinture + téléphone) — dump TOUS les crops Gemini (oui et non).
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
REPORT="$LOG_DIR/1hit-cabin-${TS}.md"
RUN_LOG="$LOG_DIR/1hit-cabin-run-${TS}.log"
EXPORT_LOG="$LOG_DIR/export-cabin-${TS}.log"

export HIT1_TS="$TS"
export VLM_CABIN_RUN="$TS"
export VLM_CABIN_DUMP_DIR="$ROOT/validation-evidence/vlm-cabin-${TS}"
export FRIGATE_VLM_BRIDGE=1
export FRIGATE_CABIN_DEDUPE_SEC="${FRIGATE_CABIN_DEDUPE_SEC:-30}"
export CABIN_MIN_CROPS="${CABIN_MIN_CROPS:-1}"
export RULE_DURATION_SEC="${RULE_DURATION_SEC:-300}"
export DEMO_ORG_ID="${DEMO_ORG_ID:-74d51ead-97a7-4e41-a488-503a9b90c466}"

mkdir -p "$VLM_CABIN_DUMP_DIR"

ensure_demo_validation_env "$ROOT" "$ROOT/.env"
_upsert_env_kv_file "$ROOT/.env" FRIGATE_VLM_BRIDGE 1
_upsert_env_kv_file "$ROOT/.env" VLM_CABIN_RUN "$TS"
_upsert_env_kv_file "$ROOT/.env" VLM_CABIN_DUMP_DIR "$VLM_CABIN_DUMP_DIR"

{
  echo "# 1-hit cabine Gemini isolé — ${TS}"
  echo ""
  echo "Démarré: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "Dump: validation-evidence/vlm-cabin-${TS}/ (YES + NO)"
  echo ""
} > "$REPORT"

echo "=== 1-hit cabin isolé TS=$TS ===" | tee "$RUN_LOG"
echo "VLM_CABIN_DUMP_DIR=$VLM_CABIN_DUMP_DIR" | tee -a "$RUN_LOG"

echo "=== restart AI (cabin dump ON, no size gate) ===" | tee -a "$RUN_LOG"
restart_ai 2>&1 | tee -a "$RUN_LOG" || { echo "[FAIL] AI restart" | tee -a "$REPORT"; exit 2; }

bash "$ROOT/scripts/ensure-demo-streams.sh" 2>&1 | tee -a "$RUN_LOG" || true
# shellcheck source=scripts/lib/service-heal.sh
source "$ROOT/scripts/lib/service-heal.sh"
ensure_backend_up 30 2>&1 | tee -a "$RUN_LOG" || true
ensure_rules_engine_up 2>&1 | tee -a "$RUN_LOG" || true

# Run seatbelt then phone sequentially so both rules get Gemini traffic.
# Canonical demo name is "Non-port ceinture" (Ceinture alone may be absent).
for RULE_NAME in 'Démo · Non-port ceinture' 'Démo · Téléphone au volant'; do
  export RULE_NAME
  export MAX_WAIT_SEC=$(( RULE_DURATION_SEC / 2 ))
  echo "=== validate $RULE_NAME (${MAX_WAIT_SEC}s) ===" | tee -a "$RUN_LOG"
  python3 -u "$ROOT/scripts/_validate_rule_frigate_1hit.py" 2>&1 | tee -a "$RUN_LOG" || true
done

# Allow queue to flush dumps
sleep 15

python3 -u "$ROOT/scripts/microtest/_export_1hit_cabin_gallery.py" 2>&1 | tee "$EXPORT_LOG" | tee -a "$RUN_LOG" || true
EXPORT_RC=${PIPESTATUS[0]:-1}
if grep -q '^OVERALL_PASS=True' "$EXPORT_LOG" 2>/dev/null; then
  EXPORT_RC=0
elif grep -q '^OVERALL_PASS=' "$EXPORT_LOG" 2>/dev/null; then
  EXPORT_RC=1
fi

GALLERY_WSL="$ROOT/validation-evidence/1hit-cabin-${TS}/index.html"
GALLERY_WIN="C:\\Users\\gheno\\citevision\\validation-evidence\\1hit-cabin-${TS}\\index.html"
DUMP_COUNT=$(find "$VLM_CABIN_DUMP_DIR" -name '*_crop.jpg' 2>/dev/null | wc -l | tr -d ' ')

if [ "$EXPORT_RC" -eq 0 ] && [ -f "$GALLERY_WSL" ] && [ "${DUMP_COUNT:-0}" -ge 1 ]; then
  STATUS=PASS
else
  STATUS=FAIL
fi

{
  echo "## Résultat: ${STATUS}"
  echo ""
  echo "| Métrique | Valeur |"
  echo "|----------|--------|"
  echo "| export_rc | ${EXPORT_RC} |"
  echo "| dump_crops | ${DUMP_COUNT} |"
  echo "| HIT1_TS | ${TS} |"
  echo "| size_gate | removed (all tracked vehicles sent) |"
  echo ""
  echo "## Galerie"
  echo "- WSL: \`validation-evidence/1hit-cabin-${TS}/index.html\`"
  echo "- Windows: \`${GALLERY_WIN}\`"
  echo "- Dump brut: \`validation-evidence/vlm-cabin-${TS}/\`"
} >> "$REPORT"

echo "=== RESULT: $STATUS dumps=${DUMP_COUNT} ===" | tee -a "$RUN_LOG"
echo "GALLERY=$GALLERY_WSL" | tee -a "$RUN_LOG"
echo "Open: $GALLERY_WIN" | tee -a "$RUN_LOG"
[ "$STATUS" = "PASS" ] && exit 0
exit 1
