#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
LOGDIR="$ROOT/logs"

echo "=== 1) dockerd natif ==="
if ! docker info >/dev/null 2>&1; then
  bash /mnt/c/Users/gheno/citevision/scripts/_start_dockerd_wsl.sh || exit 1
fi
for c in citevision-v2-postgres citevision-v2-minio citevision-v2-frigate citevision-v2-go2rtc citevision-v2-mosquitto citevision-v2-redis citevision-v2-mailhog; do
  docker start "$c" >/dev/null 2>&1 || true
done
for i in $(seq 1 30); do
  docker exec citevision-v2-postgres pg_isready -U citevision >/dev/null 2>&1 && break
  sleep 2
done
docker exec citevision-v2-postgres pg_isready -U citevision || { echo FAIL postgres; exit 1; }

echo "=== 2) services ==="
if ! curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null; then
  free_port 8081 || true
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 90 || exit 1
fi
if ! curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null; then
  bash scripts/restart-ai-engine.sh || exit 1
  for i in $(seq 1 60); do curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null && break; sleep 2; done
fi
curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null || { echo FAIL ai; exit 1; }
if ! curl -sf --max-time 3 http://127.0.0.1:8010/health >/dev/null; then
  bash scripts/_start-rules-engine.sh || true
fi
if ! curl -sf --max-time 3 http://127.0.0.1:5174/ >/dev/null; then
  bash scripts/_sync_frontend_restart_wsl.sh || exit 1
fi
curl -sf --max-time 3 http://127.0.0.1:5000/api/version >/dev/null || { echo FAIL frigate; exit 1; }

echo "=== 3) sync detection ORIGINE + preuves Frigate (pas de zones) ==="
WIN=/mnt/c/Users/gheno/citevision
# traffic_light: working HEAD classify (already restored on Windows)
python3 - <<'PY'
from pathlib import Path
win = Path("/mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai")
dst = Path("/home/gheno/citevision-v2/ai-engine/src/citevision_ai")
for rel in [
    "road_enforcement/traffic_light.py",
    "evidence/frigate_track_evidence.py",
    "pipeline.py",
]:
    t = (win / rel).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    (dst / rel).write_text(t, encoding="utf-8", newline="\n")
    print("synced", rel)
# sanity
tl = (dst / "road_enforcement/traffic_light.py").read_text()
assert "Prefer red" in tl or 'stable_state.get(camera_id) == "red"' in tl
fe = (dst / "evidence/frigate_track_evidence.py").read_text()
assert "import urllib.error" in fe
assert "AbandonedObjectDetector" in (dst / "pipeline.py").read_text()
print("sanity_ok")
PY

bash scripts/restart-ai-engine.sh
for i in $(seq 1 60); do curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null && break; sleep 2; done
curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null || { echo FAIL ai reload; tail -30 "$LOGDIR/ai-engine.log"; exit 1; }

# UI must stay up after AI restart
if ! curl -sf --max-time 3 http://127.0.0.1:5174/ >/dev/null; then
  bash scripts/_sync_frontend_restart_wsl.sh || exit 1
fi

echo "=== 4) repair streams + wait Frigate clip frais ==="
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true
echo
python3 - <<'PY'
import json, time, urllib.request
fc = "cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"
ok = False
for i in range(40):
    try:
        ev = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=8", timeout=10).read())
    except Exception as e:
        print("events_err", e); time.sleep(3); continue
    now = time.time()
    for e in (ev or []):
        if e.get("end_time") in (None, ""):
            continue
        age = now - float(e["start_time"])
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:5000/api/events/{e['id']}/clip.mp4", timeout=12
            ) as r:
                n = len(r.read(2048))
            if n > 500 and age <= 120:
                print(f"FRIGATE_READY age={age:.0f}s peek={n}")
                ok = True
                break
        except Exception as ex:
            pass
    if ok:
        break
    print(f"wait_frigate {i}")
    time.sleep(3)
raise SystemExit(0 if ok else 2)
PY
FC=$?
if [ "$FC" != "0" ]; then
  echo "Frigate media slow — restart go2rtc+frigate once"
  docker restart citevision-v2-go2rtc citevision-v2-frigate
  sleep 20
  curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true
  python3 - <<'PY'
import json, time, urllib.request
fc = "cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"
ok = False
for i in range(50):
    try:
        ev = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=8", timeout=10).read())
    except Exception as e:
        print("events_err", e); time.sleep(4); continue
    now = time.time()
    for e in (ev or []):
        if e.get("end_time") in (None, ""):
            continue
        age = now - float(e["start_time"])
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:5000/api/events/{e['id']}/clip.mp4", timeout=12
            ) as r:
                n = len(r.read(2048))
            if n > 500 and age <= 180:
                print(f"FRIGATE_READY age={age:.0f}s peek={n}")
                ok = True
                break
        except Exception:
            pass
    if ok:
        break
    print(f"wait_frigate2 {i}")
    time.sleep(4)
raise SystemExit(0 if ok else 1)
PY
fi

echo "=== STACK READY ==="
curl -sf --max-time 3 http://127.0.0.1:5174/ >/dev/null && echo UI_OK || echo UI_DOWN
curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null && echo BE_OK || echo BE_DOWN
curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null && echo AI_OK || echo AI_DOWN
curl -sf --max-time 3 http://127.0.0.1:5000/api/version >/dev/null && echo FR_OK || echo FR_DOWN
echo "UI http://127.0.0.1:5174/"
