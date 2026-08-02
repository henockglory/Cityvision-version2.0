#!/usr/bin/env bash
# Repeat 1-hit feu (test 45) N times with warm-start before each run.
# Usage: cd ~/citevision-v2 && bash scripts/microtest/_microtest_1hit_feu_stability_x3.sh
set -uo pipefail

REPO_ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$REPO_ROOT" || { echo "[FATAL] repo introuvable: $REPO_ROOT"; exit 1; }

source "$REPO_ROOT/scripts/microtest/_microtest_common.sh"

RUNS="${MICROTEST_RUNS:-3}"
COOLDOWN="${MICROTEST_COOLDOWN_SEC:-30}"
AUTO_YES="${MICROTEST_AUTO_YES:-0}"

export MICROTEST_FORCE_1HIT=1
export GATE_FEU=NO-GO
export GATE_GEMINI_FEU=NO-GO
export RULE_NAME='Démo · Feu rouge'
export RULE_ALIAS=feu

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="$REPO_ROOT/docs/microtest-stability-$TS"
WIN_OUT="/mnt/c/Users/gheno/citevision/docs/microtest-stability-$TS"
SUMMARY="$OUT_DIR/stability-summary.md"
mkdir -p "$OUT_DIR"
mkdir -p "$WIN_OUT" 2>/dev/null || true

cp_target() { cp -rf "$1" "$WIN_OUT/" 2>/dev/null || cp -f "$1" "$WIN_OUT/" 2>/dev/null || true; }

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

ensure_stack

echo "# Stability report — feu rouge — $RUNS runs — $TS" > "$SUMMARY"
echo "" >> "$SUMMARY"
echo "Chaque run : warm-start feu (90s max) → sleep 5s → \`_microtest_1hit_feu.sh\` (720s max, restart AI inclus)." >> "$SUMMARY"
echo "" >> "$SUMMARY"
echo "| Run | TEST45_RC | vlm_emitted | red_light_enqueued | skipped_not_red | align_delta_ms | warm_frames | Verdict |" >> "$SUMMARY"
echo "|---|---|---|---|---|---|---|---|" >> "$SUMMARY"

PASS_COUNT=0
FAIL_COUNT=0

for i in $(seq 1 "$RUNS"); do
  log "=================================================================="
  log "RUN $i / $RUNS"
  log "=================================================================="

  RUN_DIR="$OUT_DIR/run-$i"
  mkdir -p "$RUN_DIR"
  RUN_LOG="$RUN_DIR/1hit-feu.log"
  WARM_FRAMES="?"

  log "Warm-start caméra feu (run $i)..."
  set +e
  WARM_OUT="$(microtest_warm_feu_camera 90 2>&1 | tee "$RUN_DIR/warm-start.log")"
  WARM_RC=$?
  set -u
  if [ "$WARM_RC" -eq 0 ]; then
    WARM_FRAMES="$(echo "$WARM_OUT" | sed -n 's/.*frames=\([0-9][0-9]*\).*/\1/p' | head -1)"
    WARM_FRAMES="${WARM_FRAMES:-?}"
  else
    log "[WARN] warm-start exit=$WARM_RC — 1-hit quand même"
  fi

  sleep 5

  if [ -f "$REPO_ROOT/scripts/microtest/_microtest_1hit_feu.sh" ]; then
    log "Lancement du 1-hit feu (run $i, fenêtre max 720s)..."
    set +e
    bash "$REPO_ROOT/scripts/microtest/_microtest_1hit_feu.sh" 2>&1 | tee "$RUN_LOG"
    set -u
  else
    log "[FATAL] _microtest_1hit_feu.sh introuvable"
    echo "| $i | SCRIPT_MISSING | - | - | - | - | $WARM_FRAMES | ERROR |" >> "$SUMMARY"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    continue
  fi

  RC="$(grep -oE 'TEST45_RC=[0-9]+' "$RUN_LOG" | tail -1 | cut -d= -f2)"
  EMITTED="$(grep -oE 'vlm_queue_emitted [0-9]+' "$RUN_LOG" | tail -1 | awk '{print $2}')"
  ENQUEUED="$(grep -oE 'frigate_bridge_red_light_enqueued [0-9]+' "$RUN_LOG" | tail -1 | awk '{print $2}')"
  SKIPPED="$(grep -oE 'frigate_bridge_red_light_skipped_not_red [0-9]+' "$RUN_LOG" | tail -1 | awk '{print $2}')"
  ALIGN_MS="$(grep -oE 'align_delta_ms=[0-9]+' "$RUN_LOG" | tail -1 | cut -d= -f2)"

  RC="${RC:-?}"
  EMITTED="${EMITTED:-?}"
  ENQUEUED="${ENQUEUED:-?}"
  SKIPPED="${SKIPPED:-?}"
  ALIGN_MS="${ALIGN_MS:-?}"

  if [ "$RC" = "0" ]; then
    VERDICT="PASS_1HIT"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    VERDICT="FAIL"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi

  log "Run $i : RC=$RC emitted=$EMITTED enqueued=$ENQUEUED skipped=$SKIPPED align_ms=$ALIGN_MS warm_frames=$WARM_FRAMES → $VERDICT"
  echo "| $i | $RC | $EMITTED | $ENQUEUED | $SKIPPED | $ALIGN_MS | $WARM_FRAMES | $VERDICT |" >> "$SUMMARY"

  if [ "$i" -lt "$RUNS" ]; then
    log "Cooldown ${COOLDOWN}s..."
    sleep "$COOLDOWN"
  fi
done

echo "" >> "$SUMMARY"
echo "## Synthèse" >> "$SUMMARY"
echo "" >> "$SUMMARY"
echo "- Runs PASS_1HIT : **$PASS_COUNT / $RUNS**" >> "$SUMMARY"
echo "- Runs FAIL : **$FAIL_COUNT / $RUNS**" >> "$SUMMARY"
echo "" >> "$SUMMARY"

if [ "$PASS_COUNT" -eq "$RUNS" ]; then
  echo "**Stabilité confirmée** — $PASS_COUNT/$RUNS runs PASS_1HIT." >> "$SUMMARY"
  log "Stabilité confirmée : $PASS_COUNT/$RUNS PASS_1HIT"
elif [ "$PASS_COUNT" -eq 0 ]; then
  echo "**Aucun run réussi** — investiguer warm-start.log et 1hit-feu.log par run." >> "$SUMMARY"
  log "Aucun PASS — $FAIL_COUNT/$RUNS FAIL"
else
  echo "**Résultat mitigé** ($PASS_COUNT/$RUNS) — comparer skipped_not_red et align_delta_ms entre PASS/FAIL." >> "$SUMMARY"
  log "Mitigé : $PASS_COUNT/$RUNS PASS_1HIT"
fi

echo "" >> "$SUMMARY"
echo "Logs : \`$OUT_DIR/run-*/\`" >> "$SUMMARY"

cp_target "$SUMMARY"
for d in "$OUT_DIR"/run-*; do
  [ -d "$d" ] && cp_target "$d"
done

log ""
log "=================================================================="
log " Synthèse : $SUMMARY"
log " Windows : $WIN_OUT"
log "=================================================================="
cat "$SUMMARY"

if [ "$PASS_COUNT" -eq "$RUNS" ]; then
  exit 0
fi
exit 1
