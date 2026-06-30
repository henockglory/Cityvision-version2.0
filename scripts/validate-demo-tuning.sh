#!/usr/bin/env bash
# Re-run E2E for feu rouge + vitesse + téléphone with demo spatial tuning (10 min/rule max).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

export RULE_TIMEOUT_SEC="${RULE_TIMEOUT_SEC:-600}"
export TARGET_DETECTIONS="${TARGET_DETECTIONS:-2}"
export VALIDATE_ONLY="Démo · Feu rouge,Démo · Excès de vitesse,Démo · Téléphone au volant"

echo "==> 1/4 seed-demo-spatial (zones vidéo, tuning par défaut)"
bash "$ROOT/scripts/seed-demo-spatial.sh"

echo "==> 2/4 force spatial reload + cold start Feux/Ligne"
bash "$ROOT/scripts/force-spatial-reload.sh"

echo "==> 2b/4 restart ai-engine (traffic_light + zone_speed code)"
bash "$ROOT/scripts/restart-ai-ingest.sh" >"$ROOT/logs/restart-ai-tuning.log" 2>&1 || {
  echo "[WARN] restart-ai-ingest exited non-zero — see logs/restart-ai-tuning.log"
}
tail -15 "$ROOT/logs/restart-ai-tuning.log" || true
sleep 5

echo "==> 3/4 restart rules-engine (demo alert policy)"
stop_from_pid "$ROOT/logs/rules-engine.pid" 2>/dev/null || true
free_port "${RULES_ENGINE_PORT:-8010}" 2>/dev/null || true
GO_BIN="/usr/local/go/bin/go"
[[ -x "$GO_BIN" ]] || GO_BIN="$(command -v go)"
start_bg rules-engine "$ROOT/rules-engine" "$GO_BIN run ./cmd/rules-engine" "$ROOT/logs" "$ENV_FILE"
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${RULES_ENGINE_PORT:-8010}/health" >/dev/null 2>&1; then
    echo "[OK] rules-engine up"
    break
  fi
  sleep 2
done

echo "==> 4/4 validate tuning rules (max ${RULE_TIMEOUT_SEC}s each, stop at ${TARGET_DETECTIONS} detections)"
export PYTHONUNBUFFERED=1
exec python3 "$ROOT/scripts/validate_demo_five_rules.py"
