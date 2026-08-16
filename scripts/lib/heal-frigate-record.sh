#!/usr/bin/env bash
# Ensure Frigate demo cameras can seal event clips (record.enabled).
# Compiler sets per-camera record=true for go2rtc demo cams; this heal covers
# a stale binary / YAML that still has record.enabled: false everywhere.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRIGATE="${FRIGATE_URL:-http://127.0.0.1:5000}"
CFG="$ROOT/infra/frigate-config/config.yml"
export ROOT FRIGATE_URL="$FRIGATE" FRIGATE_CFG="$CFG"

python3 - <<'PY'
import json, os, re, sys, urllib.request, urllib.error

frigate = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000").rstrip("/")
cfg_path = os.environ.get("FRIGATE_CFG", "")
root = os.environ.get("ROOT", ".")

def live_record_on():
    try:
        with urllib.request.urlopen(frigate + "/api/config", timeout=8) as r:
            cfg = json.loads(r.read().decode())
    except Exception as e:
        print("[WARN] frigate config fetch:", e)
        return None, 0, 0
    cams = cfg.get("cameras") or {}
    on = sum(1 for c in cams.values() if (c.get("record") or {}).get("enabled"))
    glob = bool((cfg.get("record") or {}).get("enabled"))
    return glob, on, len(cams)

glob, on, n = live_record_on()
if glob is None:
    sys.exit(0)
if on > 0 or glob:
    print(f"[OK] frigate record live cameras_on={on}/{n} global={glob}")
    sys.exit(0)  # already good — skip YAML/reload; MQTT still runs below

print("[INFO] heal Frigate record.enabled (all cameras YAML false)")
p = cfg_path or os.path.join(root, "infra/frigate-config/config.yml")
if not os.path.isfile(p):
    p = os.path.expanduser("~/citevision-v2/infra/frigate-config/config.yml")
if not os.path.isfile(p):
    print("[WARN] config.yml missing — skip record heal")
    sys.exit(0)

text = open(p, encoding="utf-8", errors="replace").read()
lines = text.splitlines(True)
out = []
in_record = False
record_indent = 0
flipped = 0
for line in lines:
    m = re.match(r"^(\s*)record:\s*$", line)
    if m:
        in_record = True
        record_indent = len(m.group(1))
        out.append(line)
        continue
    if in_record:
        em = re.match(r"^(\s*)enabled:\s*(false|true)\s*$", line)
        if em and len(em.group(1)) > record_indent:
            if em.group(2) == "false":
                line = em.group(1) + "enabled: true\n"
                flipped += 1
            in_record = False
    out.append(line)
open(p, "w", encoding="utf-8").writelines(out)
print(f"[OK] patched record.enabled flipped={flipped} path={p}")
sys.exit(2)
PY
_record_rc=$?

# Reload without rebuilding the Frigate image (only if YAML was patched).
if [[ "$_record_rc" -eq 2 ]]; then
  if curl -sf --max-time 15 -X POST "${FRIGATE}/api/reload" >/dev/null 2>&1; then
    echo "[OK] frigate /api/reload"
  else
    echo "[WARN] frigate reload failed — container restart"
    docker restart citevision-v2-frigate >/dev/null 2>&1 || true
    for _ in $(seq 1 30); do
      curl -sf --max-time 3 "${FRIGATE}/api/version" >/dev/null && break
      sleep 2
    done
  fi
fi

# MQTT recordings ON only for cameras already enabled (detect gate contract).
python3 - <<'PY' || true
import json, os, sys, urllib.request
root = os.environ.get("ROOT", ".")
sys.path.insert(0, os.path.join(root, "scripts", "lib"))
frigate = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000").rstrip("/")
try:
    with urllib.request.urlopen(frigate + "/api/config", timeout=8) as r:
        cfg = json.loads(r.read().decode())
except Exception as e:
    print("[WARN] recordings MQTT skip:", e)
    raise SystemExit(0)
keep = []
for name, cam in (cfg.get("cameras") or {}).items():
    rec = bool((cam.get("record") or {}).get("enabled"))
    det = bool((cam.get("detect") or {}).get("enabled"))
    enabled = cam.get("enabled", True)
    if rec and det and enabled is not False:
        keep.append(name)
if not keep:
    print("[INFO] no enabled+record cameras for recordings MQTT")
    raise SystemExit(0)
try:
    import frigate_detect_gate as g
    g.publish_detect(keep, on=True, retain=False, kinds=("recordings",))
    print(f"[OK] MQTT recordings ON n={len(keep)}")
except Exception as e:
    print("[WARN] MQTT recordings:", e)
PY
