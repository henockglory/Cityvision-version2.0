#!/usr/bin/env bash
set -uo pipefail
ROOT=~/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

echo "=== health ==="
curl -sf --max-time 3 http://127.0.0.1:8081/health && echo " backend" || echo " backend DOWN"
curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null && echo " ai OK" || echo " ai DOWN"
curl -sf --max-time 3 http://127.0.0.1:5000/api/version && echo " frigate" || echo " frigate DOWN"

echo "=== repair-streams ==="
curl -sf -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true
echo

echo "=== frigate rebuild ==="
curl -sf -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild || true
echo

echo "=== restart frigate ==="
docker restart citevision-v2-frigate
for i in $(seq 1 40); do
  curl -sf --max-time 3 http://127.0.0.1:5000/api/version >/dev/null 2>&1 && break
  sleep 2
done
curl -sf http://127.0.0.1:5000/api/version && echo " frigate up"

FC="cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"
python3 - <<PY
import json, urllib.request, time
fc = "$FC"
# stats
try:
    cams = json.loads(urllib.request.urlopen("http://127.0.0.1:5000/api/stats", timeout=10).read()).get("cameras") or {}
    st = cams.get(fc) or {}
    print(f"frigate {fc} fps={st.get('camera_fps')} det={st.get('detection_fps')} pid={st.get('pid')}")
except Exception as e:
    print("stats", e)
# go2rtc
try:
    raw = urllib.request.urlopen("http://127.0.0.1:1984/api/streams", timeout=8).read()
    s = json.loads(raw) if raw else {}
    hits = [k for k in s if "8ed20433" in k]
    print("go2rtc hits", hits[:5], "total", len(s))
except Exception as e:
    print("go2rtc", e)

print("waiting fresh events with young clips...")
ok = False
for i in range(45):
    try:
        ev = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=5", timeout=10).read())
    except Exception as e:
        print("events_err", e)
        time.sleep(4)
        continue
    now = time.time()
    for e in (ev or []):
        age = now - float(e["start_time"])
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:5000/api/events/{e['id']}/clip.mp4", timeout=15
            ) as r:
                n = len(r.read(2048))
            if n > 500 and age <= 200:
                print(f"READY young={age:.0f}s peek={n} id={e['id'][:12]}")
                ok = True
                break
            print(f"  age={age:.0f} peek={n}")
        except Exception as ex:
            print(f"  age={age:.0f} clip_err={ex}")
    if ok:
        break
    print(f"wait {i} n={len(ev or [])}")
    time.sleep(4)
raise SystemExit(0 if ok else 1)
PY
