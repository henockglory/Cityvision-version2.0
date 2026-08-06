#!/usr/bin/env bash
# Shared helpers for micro-test campaign (WSL ~/citevision-v2).
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
AI="${AI_URL:-http://127.0.0.1:8001}"
export ROOT AI

microtest_ts() { date -u +%Y%m%dT%H%M%SZ; }

microtest_log_dir() {
  local d="$ROOT/logs/microtest-$(microtest_ts)"
  mkdir -p "$d"
  echo "$d"
}

fetch_blockers() {
  curl -sf -m 12 "$AI/debug/rule-blockers" 2>/dev/null || echo '{}'
}

fetch_health() {
  curl -sf -m 12 "$AI/health" 2>/dev/null || echo '{}'
}

bridge_stat() {
  local key="$1" json="${2:-}"
  if [ -z "$json" ]; then json="$(fetch_blockers)"; fi
  python3 - <<PY "$json" "$key"
import json, sys
d=json.loads(sys.argv[1])
fb=d.get("frigate_bridge") or {}
print(fb.get(sys.argv[2], 0))
PY
}

vlm_stat() {
  local key="$1" json="${2:-}"
  if [ -z "$json" ]; then json="$(fetch_blockers)"; fi
  python3 - <<PY "$json" "$key"
import json, sys
d=json.loads(sys.argv[1])
vq=d.get("vlm_queue") or {}
print(vq.get(sys.argv[2], 0))
PY
}

archive_blockers() {
  local label="${1:-snapshot}"
  local out="${2:-$ROOT/logs/microtest-blockers-${label}-$(microtest_ts).json}"
  fetch_blockers > "$out"
  echo "$out"
}

patch_env_kv() {
  # Delegate to permanent env-utils (no hardcoded org UUID).
  # shellcheck source=scripts/lib/env-utils.sh
  source "$ROOT/scripts/lib/env-utils.sh"
  ensure_demo_runtime_env "$ROOT" "$ROOT/.env"
  ensure_demo_validation_env "$ROOT" "$ROOT/.env"
  echo "patched $ROOT/.env via ensure_demo_validation_env"
}

resolve_gemini_model() {
  python3 - <<'PY'
from pathlib import Path
default = "gemini-3.1-flash-lite"
p = Path.home() / "citevision-v2" / ".env"
if not p.exists():
    print(default)
    raise SystemExit(0)
for line in p.read_text(encoding="utf-8").splitlines():
    if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    if k.strip() == "GEMINI_MODEL":
        m = v.strip().strip('"').strip("'")
        print(m or default)
        raise SystemExit(0)
print(default)
PY
}

set_gemini_model() {
  local model="$1"
  python3 - <<PY
from pathlib import Path
model = """$model""".strip()
p = Path.home() / "citevision-v2" / ".env"
text = p.read_text(encoding="utf-8") if p.exists() else ""
lines = text.splitlines()
seen = False
out = []
for line in lines:
    if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
        out.append(line)
        continue
    k = line.split("=", 1)[0].strip()
    if k == "GEMINI_MODEL":
        out.append(f"GEMINI_MODEL={model}")
        seen = True
    else:
        out.append(line)
if not seen:
    out.append(f"GEMINI_MODEL={model}")
p.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"GEMINI_MODEL={model}")
PY
}

restart_ai() {
  cd "$ROOT"
  python3 scripts/_restart_ai.py
  sleep 12
  for i in $(seq 1 20); do
    curl -sf -m 8 "$AI/health" >/dev/null && return 0
    sleep 3
  done
  return 1
}

smoke_stack() {
  echo "=== df /mnt/c ==="
  df -h /mnt/c | tail -1
  echo "=== frigate ==="
  curl -sf -m 5 http://127.0.0.1:5000/api/version || echo FRIGATE_FAIL
  echo "=== health ==="
  fetch_health | python3 -c "import json,sys; raw=sys.stdin.read().strip(); h=json.loads(raw) if raw else {}; print({k:h.get(k) for k in ['status','gemini_configured','gemini_model','cabin_source','vlm_queue_rate_limited']})" 2>/dev/null || echo "health_parse_fail"
  echo "=== hsv_gate_debug keys ==="
  fetch_blockers | python3 -c "import json,sys; raw=sys.stdin.read().strip(); d=json.loads(raw) if raw else {}; print('keys', list((d.get('hsv_gate_debug') or {}).keys())[:5])" 2>/dev/null || echo "blockers_parse_fail"
}

append_report() {
  local report="$1" title="$2" body="$3"
  {
    echo ""
    echo "### $title"
    echo "$body"
  } >> "$report"
}

microtest_python() {
  local py="${PYTHON:-$ROOT/ai-engine/.venv/bin/python}"
  if [ -x "$py" ]; then
    echo "$py"
  else
    echo "python3"
  fi
}

ensure_stack() {
  echo "=== ensure_stack ==="
  if ! docker info >/dev/null 2>&1; then
    bash "$ROOT/scripts/wsl-boot-stack.sh" 2>/dev/null || bash "$ROOT/scripts/health_check_all.sh" || true
  fi
  curl -sf -m 3 http://127.0.0.1:8081/health >/dev/null || bash "$ROOT/scripts/_restart_backend.sh" 2>/dev/null || true
  curl -sf -m 3 http://127.0.0.1:8001/health >/dev/null || restart_ai || true
  if ! curl -sf -m 3 "http://127.0.0.1:${RULES_ENGINE_PORT:-8010}/health" >/dev/null 2>&1; then
    bash "$ROOT/scripts/_start-rules-engine.sh" 2>/dev/null || true
    sleep 5
  fi
  for _ in $(seq 1 12); do
    curl -sf -m 5 http://127.0.0.1:5000/api/version >/dev/null && break
    sleep 5
  done
}

microtest_confirm() {
  local prompt="$1"
  if [ "${MICROTEST_AUTO_YES:-0}" = "1" ]; then
    return 0
  fi
  if [ ! -t 0 ]; then
    return 1
  fi
  read -r -p "$prompt [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]]
}

# Warm-start feu camera: resync-spatial + demo video switch + wait ingest.
# Prints: cam_id=<uuid> frames=<n> on success, empty on failure.
microtest_warm_feu_camera() {
  local max_wait="${1:-90}"
  local py
  py="$(microtest_python)"
  "$py" - <<PY
import json
import os
import sys
import time
import urllib.request

API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
AI = os.environ.get("AI_ENGINE_URL", "http://127.0.0.1:8001")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
INTERNAL = os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")
ORG = os.environ.get("DEMO_ORG_ID", "74d51ead-97a7-4e41-a488-503a9b90c466")
RULE_NAME = os.environ.get("RULE_NAME", "Démo · Feu rouge")
MAX_WAIT = int("$max_wait")


def req(method, url, token=None, body=None, internal=False):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if internal:
        headers["X-Internal-Key"] = INTERNAL
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=120) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def rule_camera_id(rule):
    defn = rule.get("definition") or {}
    if isinstance(defn, str):
        defn = json.loads(defn)
    cam = defn.get("camera_id")
    if cam:
        return str(cam)
    return str((defn.get("bindings") or {}).get("camera_id") or "")


def resolve_demo_video(token, cam_id):
    cams = req("GET", f"{API}/api/v1/orgs/{ORG}/cameras", token)
    items = cams if isinstance(cams, list) else cams.get("cameras", [])
    for c in items:
        if str(c.get("id")) == cam_id:
            meta = c.get("metadata") or {}
            if isinstance(meta, str):
                meta = json.loads(meta) if meta.startswith("{") else {}
            vid = meta.get("demo_video_id")
            return str(vid) if vid else None
    return None


def camera_frames(cam_id):
    try:
        data = req("GET", f"{AI}/cameras")
        for c in data.get("cameras", []):
            if c.get("camera_id") == cam_id:
                return int(c.get("frames_processed") or 0)
    except Exception:
        pass
    return 0


try:
    req("POST", f"{API}/api/v1/internal/ingest/resync-spatial", internal=True)
except Exception as exc:
    print(f"WARN resync-spatial: {exc}", file=sys.stderr)

login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
tok = login["access_token"]
rules = req("GET", f"{API}/api/v1/orgs/{ORG}/rules", tok)
rule = next((r for r in rules if r.get("name") == RULE_NAME), None)
if not rule:
    print("FAIL no feu rule", file=sys.stderr)
    raise SystemExit(1)
cam_id = rule_camera_id(rule)
video_id = resolve_demo_video(tok, cam_id)
if not cam_id or not video_id:
    print(f"FAIL cam={cam_id} vid={video_id}", file=sys.stderr)
    raise SystemExit(1)

req("PATCH", f"{API}/api/v1/orgs/{ORG}/demo/settings", tok, {
    "source_mode": "video",
    "active_video_id": video_id,
    "active_camera_id": None,
})
deadline = time.time() + MAX_WAIT
frames = 0
while time.time() < deadline:
    frames = camera_frames(cam_id)
    if frames >= 3:
        break
    try:
        req("POST", f"{API}/api/v1/internal/ingest/resync-spatial", internal=True)
    except Exception:
        pass
    time.sleep(6)

if frames >= 3:
    print(f"cam_id={cam_id} frames={frames}")
    raise SystemExit(0)
print(f"FAIL ingest frames={frames}", file=sys.stderr)
raise SystemExit(1)
PY
}
