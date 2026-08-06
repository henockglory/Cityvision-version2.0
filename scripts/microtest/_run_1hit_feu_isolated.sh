#!/usr/bin/env bash
# Test isolé 1-hit feu rouge — hors campagne Demo5.
# Preflight → feu seul → validate strict → galerie HTML → rapport.
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
REPORT="$LOG_DIR/1hit-feu-${TS}.md"
RUN_LOG="$LOG_DIR/1hit-feu-run-${TS}.log"
VALIDATE_LOG="$LOG_DIR/validate-feu-${TS}.log"
EXPORT_LOG="$LOG_DIR/export-feu-${TS}.log"

export HIT1_TS="$TS"
export FEU_1HIT_STRICT=1
export RED_LIGHT_GATE_MODE="${RED_LIGHT_GATE_MODE:-raw}"
export RED_LIGHT_POST_RED_GRACE_SEC="${RED_LIGHT_POST_RED_GRACE_SEC:-0}"
export RULE_ALIAS=feu
export OBSERVE_TS="$TS"
export RULE_DURATION_SEC="${RULE_DURATION_SEC:-420}"
export POLL_SEC="${POLL_SEC:-8}"
# Validation stricte : pas de bypass snapshot-seul (lf_or_g) — raw ET stable rouges exigés.
export RED_LIGHT_VOTE_MODE="${RED_LIGHT_VOTE_MODE:-strict_and}"
export RED_LIGHT_SUBJECT_MIN_TEXTURE="${RED_LIGHT_SUBJECT_MIN_TEXTURE:-50}"
export FEU_SUBJECT_TEXTURE_MIN="${FEU_SUBJECT_TEXTURE_MIN:-50}"
export EVIDENCE_SETTLE_SEC="${EVIDENCE_SETTLE_SEC:-90}"
export FEU_MIN_INGEST_FRAMES="${FEU_MIN_INGEST_FRAMES:-100}"
export PREFLIGHT_VALIDATE_LIGHT="${PREFLIGHT_VALIDATE_LIGHT:-1}"
export FEU_1HIT_REQUIRE_COMPLETE="${FEU_1HIT_REQUIRE_COMPLETE:-0}"
export FRIGATE_MAX_ALIGN_MS="${FRIGATE_MAX_ALIGN_MS:-20000}"
export OBSERVE_DURATION_SEC="$RULE_DURATION_SEC"
export OBSERVE_OUT_DIR="$LOG_DIR"
export DEMO_ORG_ID="${DEMO_ORG_ID:-74d51ead-97a7-4e41-a488-503a9b90c466}"

ensure_demo_validation_env "$ROOT" "$ROOT/.env"
_upsert_env_kv_file "$ROOT/.env" FEU_1HIT_STRICT 1

{
  echo "# 1-hit feu rouge isolé — ${TS}"
  echo ""
  echo "Démarré: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo ""
} > "$REPORT"

echo "=== 1-hit feu isolé TS=$TS ===" | tee "$RUN_LOG"

echo "=== preflight (light=${PREFLIGHT_VALIDATE_LIGHT}) ===" | tee -a "$RUN_LOG"
PREFLIGHT_VALIDATE_LIGHT="$PREFLIGHT_VALIDATE_LIGHT" bash "$ROOT/scripts/preflight-validate.sh" "$LOG_DIR/preflight-1hit-feu-${TS}.log" 2>&1 | tee -a "$RUN_LOG"

_upsert_env_kv_file "$ROOT/.env" FEU_1HIT_STRICT 1
_upsert_env_kv_file "$ROOT/.env" RED_LIGHT_GATE_MODE "$RED_LIGHT_GATE_MODE"
_upsert_env_kv_file "$ROOT/.env" RED_LIGHT_POST_RED_GRACE_SEC "$RED_LIGHT_POST_RED_GRACE_SEC"
_upsert_env_kv_file "$ROOT/.env" RED_LIGHT_VOTE_MODE "$RED_LIGHT_VOTE_MODE"

echo "=== restart AI (FEU_1HIT_STRICT=1 RED_LIGHT_VOTE_MODE=${RED_LIGHT_VOTE_MODE}) ===" | tee -a "$RUN_LOG"
restart_ai 2>&1 | tee -a "$RUN_LOG" || { echo "[FAIL] AI restart" | tee -a "$REPORT"; exit 2; }

echo "=== ensure demo streams ===" | tee -a "$RUN_LOG"
bash "$ROOT/scripts/ensure-demo-streams.sh" 2>&1 | tee -a "$RUN_LOG" || true

# shellcheck source=scripts/lib/service-heal.sh
source "$ROOT/scripts/lib/service-heal.sh"
ensure_backend_up 30 2>&1 | tee -a "$RUN_LOG" || {
  bash "$ROOT/scripts/_restart_backend.sh" 2>&1 | tee -a "$RUN_LOG" || true
  ensure_backend_up 45 2>&1 | tee -a "$RUN_LOG" || {
    echo "[FAIL] backend not up before validate" | tee -a "$REPORT"
    exit 2
  }
}

ensure_rules_engine_up 2>&1 | tee -a "$RUN_LOG" || {
  bash "$ROOT/scripts/_start-rules-engine.sh" 2>&1 | tee -a "$RUN_LOG" || true
  sleep 5
  ensure_rules_engine_up 2>&1 | tee -a "$RUN_LOG" || true
}
curl -sf -X POST "http://127.0.0.1:${RULES_ENGINE_PORT:-8010}/internal/sync-rules" 2>&1 | tee -a "$RUN_LOG" || true

echo "=== wait Frigate API (post-restart) ===" | tee -a "$RUN_LOG"
FRIGATE_DEADLINE=$(( $(date +%s) + 90 ))
until curl -sf -m 5 "http://127.0.0.1:5000/api/version" >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$FRIGATE_DEADLINE" ]; then
    echo "[FAIL] Frigate API not ready after 90s" | tee -a "$RUN_LOG"
    exit 2
  fi
  docker start citevision-v2-frigate 2>/dev/null || true
  sleep 5
done
echo "[OK] Frigate API ready" | tee -a "$RUN_LOG"

echo "=== preflight feu gate (infra + smoke evidence) ===" | tee -a "$RUN_LOG"
bash "$ROOT/scripts/microtest/_preflight_feu_gate.sh" 2>&1 | tee -a "$RUN_LOG" || {
  echo "[FAIL] preflight feu gate NO-GO" | tee -a "$REPORT"
  exit 2
}
export FEU_SKIP_FRIGATE_REBUILD=1

pkill -f '_observe_1hit_blockers.*feu' 2>/dev/null || true
python3 -u "$ROOT/scripts/_observe_1hit_blockers.py" >> "$LOG_DIR/blockers-feu-${TS}.log" 2>&1 &
OBS_PID=$!

python3 -u "$ROOT/scripts/_validate_feux_frigate_1hit.py" 2>&1 | tee "$VALIDATE_LOG" | tee -a "$RUN_LOG" || true
VALIDATE_RC=${PIPESTATUS[0]:-1}
if grep -q '^RESULT: PASS' "$VALIDATE_LOG" 2>/dev/null; then
  VALIDATE_RC=0
elif grep -q '^RESULT:' "$VALIDATE_LOG" 2>/dev/null; then
  VALIDATE_RC=1
fi

kill "$OBS_PID" 2>/dev/null || true

HIT1_SINCE="$(grep -E '^HIT1_SINCE=' "$VALIDATE_LOG" 2>/dev/null | tail -1 | cut -d= -f2- || true)"
export HIT1_SINCE
echo "HIT1_SINCE=${HIT1_SINCE:-?}" | tee -a "$RUN_LOG"

python3 -u "$ROOT/scripts/microtest/_export_1hit_feu_gallery.py" 2>&1 | tee "$EXPORT_LOG" | tee -a "$RUN_LOG" || true
EXPORT_RC=${PIPESTATUS[0]:-1}
if grep -q '^OVERALL_PASS=True' "$EXPORT_LOG" 2>/dev/null; then
  EXPORT_RC=0
elif grep -q '^OVERALL_PASS=' "$EXPORT_LOG" 2>/dev/null; then
  EXPORT_RC=1
fi

GALLERY_WSL="$ROOT/validation-evidence/1hit-feu-${TS}/index.html"
GALLERY_WIN="C:\\Users\\gheno\\citevision\\validation-evidence\\1hit-feu-${TS}\\index.html"

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
  echo "| FEU_1HIT_STRICT | 1 |"
  echo ""
  echo "## Logs"
  echo "- run: \`logs/1hit-feu-run-${TS}.log\`"
  echo "- validate: \`logs/validate-feu-${TS}.log\`"
  echo "- export: \`logs/export-feu-${TS}.log\`"
  echo "- blockers: \`logs/blockers-feu-${TS}.log\`"
  echo "- blockers-json: \`logs/blockers-feu-${TS}.json\`"
  echo "- blockers-rejects: \`logs/blockers-feu-${TS}-rejects.json\`"
  echo ""
  echo "## Galerie"
  echo "- WSL: \`validation-evidence/1hit-feu-${TS}/index.html\`"
  echo "- Windows: \`${GALLERY_WIN}\`"
  echo ""
  if [ "$STATUS" != "PASS" ]; then
    echo "## Blockers (extrait validate)"
    grep -E '\[FAIL\]|RESULT:|abort|scene_green|subject_empty|ia_overlay' "$VALIDATE_LOG" 2>/dev/null | tail -20 || true
  fi
} >> "$REPORT"

echo ""
echo "=== RESULT: $STATUS ===" | tee -a "$RUN_LOG"
echo "REPORT=$REPORT" | tee -a "$RUN_LOG"
echo "GALLERY=$GALLERY_WSL" | tee -a "$RUN_LOG"
echo "Open: $GALLERY_WIN" | tee -a "$RUN_LOG"

if [ "$STATUS" = "PASS" ]; then
  exit 0
fi
exit 1
