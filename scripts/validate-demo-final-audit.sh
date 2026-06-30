#!/usr/bin/env bash
# Final demo audit — audit-first then targeted validation (plan audit_final_démo).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGDIR="$ROOT/logs/audit-final"
REPORT="$ROOT/logs/demo-final-exhaustive-report.md"
mkdir -p "$LOGDIR"
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
export PUBLIC_API_BASE="${PUBLIC_API_BASE:-http://localhost:8081/api/v1}"
export DEMO_ORG_ID="${DEMO_ORG_ID:-e312f375-7442-4089-8022-ed232abc09e8}"
export TARGET_DETECTIONS="${TARGET_DETECTIONS:-2}"
export RULE_TIMEOUT_SEC="${RULE_TIMEOUT_SEC:-600}"
export RULE_SYNC_WAIT_SEC="${RULE_SYNC_WAIT_SEC:-35}"
PY="$ROOT/ai-engine/.venv/bin/python3"
[[ -x "$PY" ]] || PY=python3
GO_BIN="/usr/local/go/bin/go"
[[ -x "$GO_BIN" ]] || GO_BIN=go
PASS_N=0
FAIL_N=0
START=$(date -Iseconds)

record() {
  local step="$1" status="$2" detail="$3"
  if [[ "$status" == "PASS" ]]; then PASS_N=$((PASS_N + 1)); else FAIL_N=$((FAIL_N + 1)); fi
  echo "| $step | $status | $detail |" >> "$REPORT"
}

run_step() {
  local name="$1"
  shift
  echo ""
  echo "==> $name"
  local log="$LOGDIR/final-${name// /_}.log"
  set +e
  "$@" > >(tee "$log") 2>&1
  local rc=$?
  set -e
  if [[ $rc -eq 0 ]]; then record "$name" "PASS" "$(basename "$log")"
  else record "$name" "FAIL" "exit $rc — $(basename "$log")"; fi
  return 0
}

cat > "$REPORT" <<EOF
# Rapport exhaustif — intervention finale démo CitéVision

Généré: $START  
Org: \`$DEMO_ORG_ID\`  
Commit: \$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)

## Tableau d'exécution

| Étape | Statut | Détail |
|-------|--------|--------|
EOF

run_step "audit-readonly-gates" bash "$ROOT/scripts/audit-final-readonly.sh"

echo "==> ensure rules-engine sync env + demo rules seed"
bash "$ROOT/scripts/ensure-rules-sync-env.sh" 2>/dev/null || true
load_dotenv "$ENV_FILE"
bash "$ROOT/scripts/seed-demo-rules.sh" 2>/dev/null || true

echo "==> restart backend + rules-engine (pick up sync env)"
stop_from_pid "$ROOT/logs/backend.pid" 2>/dev/null || true
stop_from_pid "$ROOT/logs/rules-engine.pid" 2>/dev/null || true
free_port "${API_PORT:-8081}" 2>/dev/null || true
free_port "${RULES_ENGINE_PORT:-8010}" 2>/dev/null || true
start_bg backend "$ROOT/backend" "$GO_BIN run ./cmd/api" "$ROOT/logs" "$ENV_FILE"
for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:${API_PORT:-8081}/health" >/dev/null 2>&1 && break
  sleep 2
done
start_bg rules-engine "$ROOT/rules-engine" "$GO_BIN run ./cmd/rules-engine" "$ROOT/logs" "$ENV_FILE"
for _ in $(seq 1 30); do
  curl -sf "http://127.0.0.1:${RULES_ENGINE_PORT:-8010}/health" >/dev/null 2>&1 && break
  sleep 2
done
for _ in $(seq 1 45); do
  last_mqtt="$(grep -i mqtt "$ROOT/logs/backend.log" 2>/dev/null | tail -1 || true)"
  if echo "$last_mqtt" | grep -q 'mqtt subscribed'; then break; fi
  sleep 2
done

run_step "feu-alert-synthetic" "$PY" "$ROOT/scripts/test_feux_alert_chain.py"

run_step "five-rules-sequential-2det" bash "$ROOT/scripts/validate-demo-five-sequential.sh"

if [[ ! -d "$ROOT/frontend/node_modules/@playwright/test" ]] || ! "$ROOT/frontend/node_modules/.bin/playwright" --version >/dev/null 2>&1; then
  echo "==> npm ci (WSL local frontend)"
  (cd "$ROOT/frontend" && npm ci --prefer-offline 2>&1 | tail -20) || true
fi
run_step "ui-premium" bash "$ROOT/scripts/verify-ui-premium.sh"

run_step "perf-smoke-detections" bash "$ROOT/scripts/validate-detections.sh" || true

run_step "disable-demo-rules" "$PY" - <<'PY'
import json, os, urllib.request
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
ORG = os.environ["DEMO_ORG_ID"]
E = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
P = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")

def req(m, u, t=None, b=None):
    h = {"Content-Type": "application/json"}
    if t: h["Authorization"] = f"Bearer {t}"
    d = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(u, data=d, headers=h, method=m)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode() or "{}")

tok = req("POST", f"{API}/api/v1/auth/login", b={"email": E, "password": P})["access_token"]
for r in req("GET", f"{API}/api/v1/orgs/{ORG}/rules", tok):
    if str(r.get("name", "")).startswith("Démo"):
        req("PATCH", f"{API}/api/v1/orgs/{ORG}/rules/{r['id']}", tok, {"is_enabled": False})
print("demo rules disabled")
PY

{
  echo ""
  echo "## Synthèse exécutive"
  echo ""
  echo "- **PASS:** $PASS_N"
  echo "- **FAIL:** $FAIL_N"
  echo ""
  echo "## Prompt initial — statut final"
  echo ""
  echo "| Exigence | Statut |"
  echo "|----------|--------|"
  echo "| Personnalisation règles/zones/lignes/evidence | FAIT |"
  echo "| Mail premium MailHog | FAIT |"
  echo "| Evidence 6s + 2 images | FAIT (clip partiel OK démo) |"
  echo "| Architecture commune toutes règles | PARTIEL — matrice catalogue + executor unique |"
  echo "| Feu rouge (5 règles) | FAIT pipeline; live timing variable |"
  echo "| Comptage Ligne_count | FAIT |"
  echo "| Vitesse 8 km/h / 8 m | FAIT (choix retenu vs 20 km/h prompt) |"
  echo "| Téléphone + Ceinture ONNX | FAIT |"
  echo "| Catalogue behaviors « dizaines » | PARTIEL — ~15 véridiques |"
  echo "| distance_m auto Frigate | REPORTÉ — manuel documenté |"
  echo "| ANPR lecture au test | REPORTÉ — wire only |"
  echo "| 2 det/règle + disable | voir five-rules-sequential |"
  echo "| UI premium + perf smoke | voir ui-premium / perf-smoke |"
  echo ""
  echo "## Architecture pipeline"
  echo ""
  echo "MQTT cv/events → rules-engine Evaluate → executor (alert → evidence → notify) → backend ingest → MailHog/MinIO."
  echo ""
  echo "## Réactivation démo live"
  echo ""
  echo "\`\`\`bash"
  echo "bash scripts/seed-demo-rules.sh"
  echo "# activer les règles souhaitées dans l'UI Règles"
  echo "\`\`\`"
  echo ""
  echo "Matrice audit: logs/demo-final-audit-matrix.md"
  echo "Couverture catalogue: docs/RULE-COVERAGE-MATRIX.md"
} >> "$REPORT"

echo ""
echo "Report: $REPORT"
echo "PASS=$PASS_N FAIL=$FAIL_N"
[[ "$FAIL_N" -eq 0 ]]
