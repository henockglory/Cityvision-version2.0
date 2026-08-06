#!/usr/bin/env bash
# Permanent preflight before validate_rule / install-gate — no microtest campaign deps.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export ROOT

if [[ "$ROOT" == /mnt/c/* ]] || [[ "$ROOT" == /mnt/d/* ]]; then
  echo "[FAIL] preflight-validate refuse ROOT under /mnt/* (got $ROOT)."
  echo "       Run from native WSL: cd ~/citevision-v2 && bash scripts/preflight-validate.sh"
  exit 1
fi

export PATH="${ROOT}/ai-engine/.venv/bin:${PATH:-}"
LOG="${1:-$ROOT/logs/preflight-validate.log}"
mkdir -p "$(dirname "$LOG")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
API="${BACKEND_API_URL:-http://127.0.0.1:8081}"
AI="${AI_URL:-http://127.0.0.1:8001}"
LIGHT="${PREFLIGHT_VALIDATE_LIGHT:-0}"

# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
# shellcheck source=scripts/lib/service-heal.sh
source "$ROOT/scripts/lib/service-heal.sh"

log() { echo "$@" | tee -a "$LOG"; }

log "=== preflight-validate start (light=$LIGHT) ==="

ENV_FILE="$(ensure_env_file "$ROOT" 2>/dev/null || echo "$ROOT/.env")"
ensure_demo_runtime_env "$ROOT" "$ENV_FILE" 2>&1 | tee -a "$LOG"
ensure_frigate_paths_env "$ROOT" "$ENV_FILE" 2>&1 | tee -a "$LOG"
ensure_gemini_key_env "$ROOT" "$ENV_FILE" 2>&1 | tee -a "$LOG" || {
  log "[WARN] GEMINI_API_KEY missing — cabin VLM may be disabled"
}

log "=== ensure services ==="
if ! ensure_backend_up 30 >>"$LOG" 2>&1; then
  bash "$ROOT/scripts/_restart_backend.sh" >>"$LOG" 2>&1 || true
  ensure_backend_up 30 >>"$LOG" 2>&1 || { log "[FAIL] backend not up"; exit 2; }
fi

if [[ "$LIGHT" != "1" ]]; then
  restart_ai_engine 2>&1 | tee -a "$LOG" || { log "[FAIL] AI restart"; exit 2; }
  log "=== wait gemini reachable (best-effort) ==="
  for i in $(seq 1 24); do
    ok=$(curl -sf -m 12 "$AI/health" 2>/dev/null \
      | python3 -c "import json,sys; h=json.load(sys.stdin); print('1' if str(h.get('gemini_reachable','')).lower() in ('true','1','yes') else '0')" 2>/dev/null || echo 0)
    if [ "$ok" = "1" ]; then
      log "gemini_reachable OK attempt=$i"
      break
    fi
    log "  waiting gemini_reachable ($i/24)..."
    sleep 5
  done
else
  ensure_ai_up 2>&1 | tee -a "$LOG" || true
fi

ensure_rules_engine_up 2>&1 | tee -a "$LOG" || true

if [[ "$LIGHT" != "1" ]]; then
  log "=== demo streams + frigate rebuild ==="
  bash "$ROOT/scripts/ensure-demo-streams.sh" 2>&1 | tee -a "$LOG" || true
  REBUILD='{"status":"error"}'
  for attempt in 1 2 3; do
    curl -sf -m 5 "$API/health" >/dev/null || bash "$ROOT/scripts/_restart_backend.sh" 2>&1 | tee -a "$LOG"
    sleep 3
    curl -sf -X POST -H "X-Internal-Key: $KEY" \
      "$API/api/v1/internal/demo/repair-streams" 2>&1 | tee -a "$LOG" || true
    curl -sf -X POST -H "X-Internal-Key: $KEY" \
      "$API/api/v1/internal/ingest/resync-spatial" 2>&1 | tee -a "$LOG" || true
    REBUILD=$(curl -sf -X POST -H "X-Internal-Key: $KEY" \
      "$API/api/v1/internal/ingest/frigate/rebuild" 2>&1 || echo '{"status":"error"}')
    log "frigate_rebuild attempt=$attempt: $REBUILD"
    if echo "$REBUILD" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='ok' else 1)"; then
      break
    fi
    sleep 10
  done
  if ! echo "$REBUILD" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='ok' else 1)"; then
    log "[WARN] frigate rebuild not ok: $REBUILD"
  fi
  nc=$(curl -sf http://127.0.0.1:5000/api/stats 2>/dev/null \
    | python3 -c "import json,sys; print(len((json.load(sys.stdin).get('cameras') or {})))" 2>/dev/null || echo 0)
  if [ "${nc:-0}" -lt 4 ]; then
    log "Frigate cameras=$nc — docker restart frigate"
    docker restart citevision-v2-frigate >/dev/null 2>&1 || true
    sleep 25
  fi
fi

python3 - <<'PY' | tee -a "$LOG"
import json, os, sys, urllib.request
from pathlib import Path

errors = []
warns = []

def get(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as exc:
        return {"_err": str(exc)}

ai = get("http://127.0.0.1:8001/health")
if str(ai.get("gemini_configured", "")).lower() not in ("true", "1", "yes"):
    warns.append(f"gemini_configured={ai.get('gemini_configured')}")
reach = str(ai.get("gemini_reachable", "")).lower()
if reach not in ("true", "1", "yes"):
    if str(ai.get("gemini_configured", "")).lower() in ("true", "1", "yes"):
        warns.append("gemini_reachable=false (configured=true)")
    else:
        errors.append(f"gemini_reachable={ai.get('gemini_reachable')}")
if str(ai.get("models_all_ok", "")).lower() not in ("true", "1", "yes"):
    errors.append(f"models_all_ok={ai.get('models_all_ok')}")

fr = get("http://127.0.0.1:8081/health/frigate")
if str(fr.get("enabled", "")).lower() not in ("true", "1", "yes"):
    errors.append(f"frigate_enabled={fr.get('enabled')}")

stats = get("http://127.0.0.1:5000/api/stats")
nc = len((stats.get("cameras") or {}))
if nc < 4:
    errors.append(f"frigate_cameras={nc} (need>=4)")

re = get("http://127.0.0.1:8010/health")
if re.get("status") != "ok":
    errors.append(f"rules_engine={re.get('status')}")

env = Path(os.environ.get("ROOT", ".")) / ".env"
if not env.is_file():
    env = Path.home() / "citevision-v2" / ".env"
org = ""
if env.is_file():
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("DEFAULT_ORG_ID="):
            org = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
if not org:
    warns.append("DEFAULT_ORG_ID unset (run ensure-rules-sync-env --resolve-org)")

cams = get("http://127.0.0.1:8001/cameras")
items = cams.get("cameras") or []
adv = [c for c in items if int(c.get("frames_processed") or 0) >= 1]
if not adv and os.environ.get("PREFLIGHT_VALIDATE_LIGHT", "0") != "1":
    warns.append("ingest_no_frames_yet")

for w in warns:
    print(f"WARN {w}")
if errors:
    print("PREFLIGHT_VALIDATE_FAIL:", "; ".join(errors))
    sys.exit(2)
print("PREFLIGHT_VALIDATE_OK frigate_cameras=", nc, "ingest_cams=", len(adv))
PY

log "=== preflight-validate OK ==="
