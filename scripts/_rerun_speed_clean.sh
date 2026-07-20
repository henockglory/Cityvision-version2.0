#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cd "$ROOT"
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"

source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
LOGDIR=$ROOT/logs

echo "=== 1) sync evidence code ==="
cp -f "$WIN/ai-engine/src/citevision_ai/evidence/service.py" \
  "$ROOT/ai-engine/src/citevision_ai/evidence/service.py"
cp -f "$WIN/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py" \
  "$ROOT/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py"
cp -f "$WIN/ai-engine/src/citevision_ai/config.py" \
  "$ROOT/ai-engine/src/citevision_ai/config.py"
cp -f "$WIN/scripts/_validate_rule_frigate_1hit.py" \
  "$ROOT/scripts/_validate_rule_frigate_1hit.py"
sed -i 's/\r$//' \
  "$ROOT/ai-engine/src/citevision_ai/evidence/"*.py \
  "$ROOT/ai-engine/src/citevision_ai/config.py" \
  "$ROOT/scripts/_validate_rule_frigate_1hit.py"

# ensure align env
if grep -q '^FRIGATE_DEMO_ACCEPT_MAX_ALIGN_SEC=' "$ENV_FILE"; then
  sed -i 's/^FRIGATE_DEMO_ACCEPT_MAX_ALIGN_SEC=.*/FRIGATE_DEMO_ACCEPT_MAX_ALIGN_SEC=20/' "$ENV_FILE"
else
  echo 'FRIGATE_DEMO_ACCEPT_MAX_ALIGN_SEC=20' >> "$ENV_FILE"
fi

echo "=== 2) ensure backend/AI/rules/frigate ==="
if ! curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null; then
  free_port 8081 || true
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 90
fi
if ! curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null; then
  bash scripts/restart-ai-engine.sh
fi
if ! curl -sf --max-time 3 http://127.0.0.1:8010/health >/dev/null; then
  bash scripts/_start-rules-engine.sh || true
fi
curl -sf http://127.0.0.1:5000/api/version >/dev/null || {
  echo "Frigate down — attempting docker start"
  docker start citevision-v2-frigate || true
  sleep 15
}

echo "=== 3) restart AI clean (load latest evidence code) ==="
: > "$ROOT/logs/ai-engine.log"
bash scripts/restart-ai-engine.sh
for i in $(seq 1 45); do
  curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null && break
  sleep 2
done
curl -sf http://127.0.0.1:8001/health | python3 -c 'import sys,json; d=json.load(sys.stdin); assert str(d.get("models_all_ok")).lower()=="true"'

# backend often dies on AI restart
if ! curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null; then
  free_port 8081 || true
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 90
fi
if ! curl -sf --max-time 3 http://127.0.0.1:8010/health >/dev/null; then
  bash scripts/_start-rules-engine.sh || true
fi

curl -sf -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true

echo "=== 4) ensure frontend :5174 ==="
if ! curl -sf --max-time 3 http://127.0.0.1:5174/ >/dev/null; then
  bash scripts/_sync_frontend_restart_wsl.sh || {
    stop_from_pid "$LOGDIR/frontend.pid" 2>/dev/null || true
    free_port 5174 || true
    start_bg frontend "$ROOT/frontend" "npm run dev -- --host 0.0.0.0 --port 5174 --strictPort" "$LOGDIR" "$ENV_FILE"
    wait_http_ok http://127.0.0.1:5174/ 90
  }
fi
curl -sf http://127.0.0.1:5174/ >/dev/null && echo "frontend_ok"
curl -sf http://127.0.0.1:5174/health && echo || echo "WARN vite->backend /health failed"

echo "=== 5) frigate media precheck ==="
python3 <<'PY'
import json, urllib.request, time, urllib.error
fc = "cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
ok = False
for i in range(20):
    try:
        ev = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=3", timeout=8
        ).read())
    except Exception as e:
        print(f"events_err {e}"); time.sleep(4); continue
    if not ev:
        print("no_events"); time.sleep(4); continue
    eid = ev[0]["id"]
    young = time.time() - float(ev[0]["start_time"])
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:5000/api/events/{eid}/clip.mp4", timeout=20) as r:
            n = len(r.read(4096)); code = 200
    except urllib.error.HTTPError as e:
        code, n = e.code, 0
    except Exception:
        code, n = -1, 0
    print(f"precheck {i} young={young:.0f}s http={code} peek={n}")
    if young <= 120 and code == 200 and n > 500:
        ok = True; break
    time.sleep(4)
assert ok, "frigate clip not ready"
print("media_ready")
PY

python3 scripts/_reset_demo_password.py 'Hologram2026!' || true

echo "=== 6) validate 1-hit speed (no frigate rebuild) ==="
export ADMIN_PASSWORD='Hologram2026!'
export RULE_NAME='Démo · Excès de vitesse'
export TARGET_DETECTIONS=1
export RULE_DURATION_SEC=360
export SKIP_FRIGATE_REBUILD=1
export PYTHONUNBUFFERED=1
set +e
python3 scripts/_validate_rule_frigate_1hit.py
VC=$?
set -e
echo "VALIDATE_EXIT=$VC"

echo "=== 7) post-check alerts + frontend ==="
python3 <<'PY'
import json, urllib.request, urllib.error
ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
CAM = "55694d53-8f58-4981-91b2-7c6cd528a25d"
body = json.dumps({"email":"glory.henock@hologram.cd","password":"Hologram2026!"}).encode()
tok = json.loads(urllib.request.urlopen(urllib.request.Request(
    "http://127.0.0.1:8081/api/v1/auth/login", data=body,
    headers={"Content-Type":"application/json"}, method="POST"), timeout=15).read())["access_token"]
h = {"Authorization": f"Bearer {tok}"}
raw = json.loads(urllib.request.urlopen(urllib.request.Request(
    f"http://127.0.0.1:8081/api/v1/orgs/{ORG}/alerts?limit=5&camera_id={CAM}",
    headers=h), timeout=20).read())
items = raw if isinstance(raw, list) else raw.get("alerts") or raw.get("items") or []
ft = 0
for a in items[:5]:
    snap = a.get("evidence_snapshot") or {}
    if isinstance(snap, str):
        try: snap = json.loads(snap)
        except Exception: snap = {}
    pkg = snap.get("package") or {}
    meta = pkg.get("metadata") if isinstance(pkg, dict) else {}
    src = (meta or {}).get("capture_source")
    imgs = pkg.get("images") if isinstance(pkg, dict) else []
    roles = [i.get("role") for i in (imgs or []) if isinstance(i, dict) and (i.get("url") or i.get("asset_id"))]
    clip = pkg.get("clip") if isinstance(pkg, dict) else {}
    has_clip = bool(isinstance(clip, dict) and (clip.get("url") or clip.get("asset_id")))
    print(f"alert id={str(a.get('id',''))[:8]} src={src} roles={roles} clip={has_clip}")
    if src == "frigate_track" and has_clip and "scene" in roles and "subject" in roles:
        ft += 1
print(f"frigate_complete_alerts={ft}")
try:
    urllib.request.urlopen("http://127.0.0.1:5174/", timeout=5)
    print("frontend_5174=OK")
except Exception as e:
    print(f"frontend_5174=FAIL {e}")
try:
    urllib.request.urlopen("http://127.0.0.1:5174/health", timeout=5)
    print("frontend_proxy_backend=OK")
except Exception as e:
    print(f"frontend_proxy_backend=FAIL {e}")
raise SystemExit(0 if ft >= 1 else 1)
PY

exit $VC
