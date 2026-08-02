#!/usr/bin/env bash
# Tests 41-44 / 51-54: shadow synergy LF_OR_G vs strict_and.
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
source scripts/microtest/_microtest_common.sh
REPORT="${MICROTEST_REPORT:-$ROOT/logs/microtest-report-$(microtest_ts).md}"

VOTE_MODE="${RED_LIGHT_VOTE_MODE:-lf_or_g}"
SHADOW_SEC="${MICROTEST_SHADOW_SEC:-120}"

patch_synergy_env() {
  python3 - <<PY
from pathlib import Path
import re
p = Path.home() / "citevision-v2" / ".env"
t = p.read_text(encoding="utf-8") if p.exists() else ""
updates = {
    "RED_LIGHT_VOTE_MODE": "${VOTE_MODE}",
    "RED_LIGHT_VOTE_SHADOW": "1",
    "GEMINI_SHADOW_MODE": "1",
    "RED_LIGHT_DEBUG_FORCE_ENQUEUE": "0",
}
for k, v in updates.items():
    if re.search(rf"^{k}=", t, flags=re.M):
        t = re.sub(rf"^{k}=.*$", f"{k}={v}", t, flags=re.M)
    else:
        t += f"\n{k}={v}\n"
p.write_text(t, encoding="utf-8")
print(f"vote_mode=${VOTE_MODE} shadow=1")
PY
}

patch_synergy_env
microtest_warm_feu_camera || true
restart_ai || true
sleep "$SHADOW_SEC"

B="$(fetch_blockers)"
BR="$(python3 - <<PY
import json, sys
d = json.loads('''$B''')
br = d.get("frigate_bridge") or {}
print(
    f"lf_or_g_would_emit={br.get('lf_or_g_would_emit', 0)} "
    f"lf_or_g_shadow={br.get('lf_or_g_shadow', 0)} "
    f"red_light_enqueued={br.get('red_light_enqueued', 0)}"
)
PY
)"
VQ="$(python3 - <<PY
import json, sys
d = json.loads('''$B''')
vq = d.get("vlm_queue") or {}
print(f"shadow_logged={vq.get('shadow_logged', 0)} rejected={vq.get('rejected', 0)}")
PY
)"

append_report "$REPORT" "Tests 51-54 LF_OR_G shadow" "vote=${VOTE_MODE} ${BR} ${VQ}"
echo "synergy ${BR} ${VQ}"

# restore campaign defaults (strict_and, no vote shadow)
python3 - <<'PY'
from pathlib import Path
import re
p = Path.home() / "citevision-v2" / ".env"
if not p.exists():
    raise SystemExit(0)
t = p.read_text(encoding="utf-8")
for k, v in [
    ("RED_LIGHT_VOTE_MODE", "strict_and"),
    ("RED_LIGHT_VOTE_SHADOW", "0"),
    ("GEMINI_SHADOW_MODE", "0"),
]:
    if re.search(rf"^{k}=", t, flags=re.M):
        t = re.sub(rf"^{k}=.*$", f"{k}={v}", t, flags=re.M)
p.write_text(t, encoding="utf-8")
PY
restart_ai || true
