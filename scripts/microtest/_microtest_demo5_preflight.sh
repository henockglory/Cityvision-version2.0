#!/usr/bin/env bash
# Demo5 preflight — delegates to permanent preflight-validate + campaign gates.
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
export PATH="${ROOT}/ai-engine/.venv/bin:${PATH}"
export DEMO_ORG_ID="${DEMO_ORG_ID:-74d51ead-97a7-4e41-a488-503a9b90c466}"
LOG="${1:-$ROOT/logs/demo5-preflight.log}"
mkdir -p "$(dirname "$LOG")"

source "$ROOT/scripts/microtest/_microtest_common.sh"
source "$ROOT/scripts/lib/env-utils.sh"

log() { echo "$@" | tee -a "$LOG"; }

assert_demo_org_gate() {
  python3 - <<PY | tee -a "$LOG"
import os
from pathlib import Path

demo_org = os.environ.get("DEMO_ORG_ID", "").strip()
env = Path("$ROOT/.env")
org = ""
if env.is_file():
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("DEFAULT_ORG_ID="):
            org = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
if demo_org and org and org != demo_org:
    print(f"PREFLIGHT_GATES_FAIL: DEFAULT_ORG_ID={org!r} expected {demo_org!r}")
    raise SystemExit(2)
print(f"PREFLIGHT_DEMO_ORG_OK org={org or demo_org}")
PY
}

log "=== Demo5 preflight start ==="
bash "$ROOT/scripts/health_check_all.sh" 2>&1 | tee -a "$LOG" || true

patch_env_kv 2>&1 | tee -a "$LOG"
ensure_gemini_key_env "$ROOT" "$ROOT/.env" 2>&1 | tee -a "$LOG" || {
  log "[FAIL] GEMINI_API_KEY missing — set in ~/citevision-v2/.env or GEMINI_KEY_FILE"
  exit 2
}

bash "$ROOT/scripts/preflight-validate.sh" "$LOG" || {
  log "[FAIL] preflight-validate"
  exit 2
}

assert_demo_org_gate || exit 2
log "=== Demo5 preflight OK ==="
