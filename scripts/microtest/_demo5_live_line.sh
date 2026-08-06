#!/usr/bin/env bash
# One-line JSON status for Demo5 live chat polling (read-only).
set -uo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
AI="${AI_URL:-http://127.0.0.1:8001}"
STEP="${DEMO5_CURRENT_STEP:-?}"
ALIAS="${DEMO5_CURRENT_ALIAS:-?}"
CAMPAIGN_LOG="${DEMO5_CAMPAIGN_LOG:-}"

python3 - <<'PY'
import json, os, time, urllib.request

ai = "http://127.0.0.1:8001"
step = os.environ.get("DEMO5_CURRENT_STEP", "?")
alias = os.environ.get("DEMO5_CURRENT_ALIAS", "?")
log_path = os.environ.get("DEMO5_CAMPAIGN_LOG", "")

def get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as exc:
        return {"_err": str(exc)}

h = get(f"{ai}/health")
b = get(f"{ai}/debug/rule-blockers")
stats = get("http://127.0.0.1:5000/api/stats")
vq = b.get("vlm_queue") or {}
fb = b.get("frigate_bridge") or {}

tail = ""
if log_path and os.path.isfile(log_path):
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        tail = (lines[-1].strip() if lines else "")[:120]
    except OSError:
        pass

out = {
    "ts": time.strftime("%H:%M:%S", time.gmtime()),
    "step": step,
    "alias": alias,
    "gemini": h.get("gemini_configured"),
    "gemini_reachable": h.get("gemini_reachable"),
    "frigate_cams": len((stats.get("cameras") or {})),
    "vlm_enqueued": vq.get("enqueued"),
    "vlm_completed": vq.get("completed"),
    "vlm_rejected": vq.get("rejected"),
    "vlm_emitted": vq.get("emitted"),
    "cabin_enqueued": fb.get("cabin_enqueued"),
    "log_tail": tail,
}
print(json.dumps(out, ensure_ascii=False))
PY
