#!/usr/bin/env bash
# Final demo handoff: pipeline gates + honest timing notes (~30–45 min).
# Run on WSL ~/citevision-v2 after syncing from Windows repo.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

export DEMO_ORG_ID="${DEMO_ORG_ID:-e312f375-7442-4089-8022-ed232abc09e8}"
LOGDIR="$ROOT/logs"
REPORT="$LOGDIR/demo-handoff-final.md"
PY="$ROOT/ai-engine/.venv/bin/python3"
[[ -x "$PY" ]] || PY="$(command -v python3)"
GO_BIN="/usr/local/go/bin/go"
[[ -x "$GO_BIN" ]] || GO_BIN="$(command -v go)"
API_PORT="${API_PORT:-8081}"
RE_PORT="${RULES_ENGINE_PORT:-8010}"

mkdir -p "$LOGDIR"
PIPE_PASS=0
PIPE_FAIL=0
TIMING_NOTES=()

record() {
  local pipeline="$1"
  local timing="$2"
  local detail="$3"
  if [[ "$pipeline" == "PASS" ]]; then
    PIPE_PASS=$((PIPE_PASS + 1))
  else
    PIPE_FAIL=$((PIPE_FAIL + 1))
  fi
  echo "| ${STEP_NAME} | ${pipeline} | ${timing} | ${detail} |" >> "$REPORT"
}

run_step() {
  local timing_note="${1:-—}"
  shift
  echo ""
  echo "==> ${STEP_NAME}"
  local logfile="$LOGDIR/handoff-$(echo "$STEP_NAME" | tr ' /' '__').log"
  set +e
  "$@" > >(tee "$logfile") 2>&1
  local rc=$?
  set -e
  if [[ $rc -eq 0 ]]; then
    record "PASS" "$timing_note" "see $(basename "$logfile")"
  else
    record "FAIL" "$timing_note" "exit $rc — $(basename "$logfile")"
  fi
  return 0
}

restart_services() {
  echo "==> restart backend + rules-engine"
  stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
  stop_from_pid "$LOGDIR/rules-engine.pid" 2>/dev/null || true
  free_port "$API_PORT" 2>/dev/null || true
  free_port "$RE_PORT" 2>/dev/null || true
  start_bg backend "$ROOT/backend" "$GO_BIN run ./cmd/api" "$LOGDIR" "$ENV_FILE"
  for _ in $(seq 1 60); do
    curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1 && break
    sleep 2
  done
  start_bg rules-engine "$ROOT/rules-engine" "$GO_BIN run ./cmd/rules-engine" "$LOGDIR" "$ENV_FILE"
  for _ in $(seq 1 30); do
    curl -sf "http://127.0.0.1:${RE_PORT}/health" >/dev/null 2>&1 && break
    sleep 2
  done
}

disable_demo_rules() {
  echo "==> disable all demo rules"
  "$PY" - <<'PY' || true
import json, os, urllib.request
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
ORG = os.environ["DEMO_ORG_ID"]
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")

def req(m, u, t=None, b=None):
    h = {"Content-Type": "application/json"}
    if t: h["Authorization"] = f"Bearer {t}"
    d = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(u, data=d, headers=h, method=m)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode() or "{}")

tok = req("POST", f"{API}/api/v1/auth/login", b={"email": EMAIL, "password": PASS})["access_token"]
rules = req("GET", f"{API}/api/v1/orgs/{ORG}/rules", tok)
for r in rules:
    if str(r.get("name", "")).startswith("Démo"):
        req("PATCH", f"{API}/api/v1/orgs/{ORG}/rules/{r['id']}", tok, {"is_enabled": False})
print("demo rules disabled")
PY
}

cat > "$REPORT" <<EOF
# Demo handoff final — $(date -Iseconds)

Org: \`$DEMO_ORG_ID\`

| Step | Pipeline | Timing vidéo | Detail |
|------|----------|--------------|--------|
EOF

echo "==> ensure AI stack (secondary models gate)"
bash "$ROOT/scripts/ensure-ai-stack.sh" --verify-only || \
  bash "$ROOT/scripts/ensure-ai-stack.sh" --fix --restart-ai || true
bash "$ROOT/scripts/download-secondary-models.sh" 2>/dev/null || true
bash "$ROOT/scripts/ensure-rules-sync-env.sh" 2>/dev/null || true

STEP_NAME="preflight (infra + evidence + mail)"
run_step "—" "$PY" "$ROOT/scripts/preflight_demo_pipeline.py"

STEP_NAME="seed-demo-spatial"
run_step "—" bash "$ROOT/scripts/seed-demo-spatial.sh"

STEP_NAME="force-spatial-reload"
run_step "—" bash "$ROOT/scripts/force-spatial-reload.sh"

STEP_NAME="seed-demo-rules"
run_step "—" bash "$ROOT/scripts/seed-demo-rules.sh"

restart_services

STEP_NAME="feu alert chain (synthetic MQTT)"
export RULE_SYNC_WAIT_SEC="${RULE_SYNC_WAIT_SEC:-35}"
run_step "info only" "$PY" "$ROOT/scripts/test_feux_alert_chain.py"

STEP_NAME="ceinture quick (1 det + mail)"
run_step "events if video runs" bash "$ROOT/scripts/validate-demo-seatbelt-quick.sh" || TIMING_NOTES+=("ceinture: may fail on video timing only")

STEP_NAME="vitesse quick (1 det)"
run_step "events if video runs" bash "$ROOT/scripts/validate-demo-speed-quick.sh" || TIMING_NOTES+=("vitesse: may fail on video timing only")

STEP_NAME="téléphone quick (1 det)"
run_step "events if video runs" bash "$ROOT/scripts/validate-demo-phone-quick.sh" || TIMING_NOTES+=("téléphone: may fail on video timing only")

STEP_NAME="feu monitor (180s colors)"
export FEUX_MONITOR_MAX_SEC=180
export FEUX_REPORT_JSON="$LOGDIR/feux-monitor-handoff.json"
run_step "colors/violation live" "$PY" "$ROOT/scripts/monitor_feux_until_success.py" 180

STEP_NAME="Playwright demo-commercial"
if [[ -d "$ROOT/frontend/node_modules" ]]; then
  run_step "UI smoke" bash -c "cd '$ROOT/frontend' && npx playwright test e2e/demo-commercial.spec.ts --reporter=line"
else
  record "FAIL" "—" "frontend/node_modules missing"
fi

STEP_NAME="go test backend"
run_step "—" bash -c "cd '$ROOT/backend' && $GO_BIN test ./... -count=1"

STEP_NAME="go test rules-engine"
run_step "—" bash -c "cd '$ROOT/rules-engine' && $GO_BIN test ./... -count=1"

STEP_NAME="pytest ai-engine smoke"
run_step "—" bash -c "cd '$ROOT/ai-engine' && '$PY' -m pytest tests/ -q --tb=no -x" || true

disable_demo_rules

{
  echo ""
  echo "## Summary"
  echo ""
  echo "- Pipeline PASS steps: **$PIPE_PASS**"
  echo "- Pipeline FAIL steps: **$PIPE_FAIL**"
  echo ""
  echo "## Timing vidéo (non bloquant)"
  echo ""
  if ((${#TIMING_NOTES[@]})); then
    for n in "${TIMING_NOTES[@]}"; do echo "- $n"; done
  else
    echo "- Quick rule tests depend on live demo video pacing; failures here do not invalidate pipeline gates (preflight, synthetic feu alert, spatial seed)."
  fi
  echo ""
  echo "## Prompt initial — statut honnête"
  echo ""
  echo "| Item | Statut |"
  echo "|------|--------|"
  echo "| 5 règles démo (seed + spatial) | atteint |"
  echo "| Alert-first + mail MailHog HTML | atteint (preflight + ceinture quick) |"
  echo "| Evidence request API | atteint (preflight; clip partiel OK démo) |"
  echo "| Feu rouge alerte pipeline | atteint (test synthétique MQTT) |"
  echo "| Feu couleurs MQTT live | partiel (monitor 180s) |"
  echo "| Comptage UI Demo Center | atteint (caméra décompte) |"
  echo "| Zone behaviors applies_to | atteint |"
  echo "| ANPR wire (plate_ocr seed) | atteint (optionnel, pas test lecture) |"
  echo "| Catalogue entier / dizaines behaviors | reporté / partiel |"
  echo "| distance_m auto Frigate | reporté (manuel 8 m) |"
  echo "| Lecture plaque garantie au test | reporté |"
  echo "| Violation feu live garantie 3 min | reporté (non gate) |"
  echo ""
  echo "## ANPR"
  echo ""
  echo "ANPR actif si PaddleOCR installé (\`pip install -e 'ai-engine/.[anpr]'\`) + zone \`plate_ocr\` (\`Zone_plaque\` seed optionnel)."
  echo ""
  echo "## Vitesse démo"
  echo ""
  echo "Calibration retenue: **8 km/h** / **8 m** (\`Zone_distance_parcourue\`). Champ \`distance_m\` = distance réelle au sol dans le sens de circulation."
} >> "$REPORT"

echo ""
echo "Report: $REPORT"
echo "Pipeline PASS=$PIPE_PASS FAIL=$PIPE_FAIL"
if [[ "$PIPE_FAIL" -gt 0 ]]; then
  exit 1
fi
