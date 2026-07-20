#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
FC=cv_8ed20433-57d5-4999-a6ab-0bea028b23a3

echo "=== frigate stats ==="
python3 - <<PY
import json,urllib.request
fc="$FC"
try:
  st=json.loads(urllib.request.urlopen("http://127.0.0.1:5000/api/stats",timeout=8).read())
  cam=(st.get("cameras") or {}).get(fc) or {}
  print("fps",cam.get("camera_fps"),"det",cam.get("detection_fps"),"pid",cam.get("pid"))
except Exception as e:
  print("stats",e)
PY

echo "=== repair + restart go2rtc/frigate ==="
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams; echo
docker restart citevision-v2-go2rtc
sleep 5
docker restart citevision-v2-frigate
for i in $(seq 1 40); do
  curl -sf --max-time 3 http://127.0.0.1:5000/api/version >/dev/null && break
  sleep 2
done
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams; echo

echo "=== wait young event ==="
python3 - <<'PY'
import json,time,urllib.request
fc="cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"
for i in range(60):
  try:
    ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=5",timeout=10).read())
  except Exception as e:
    print("err",e); time.sleep(3); continue
  now=time.time()
  ages=[]
  for e in (ev or []):
    age=now-float(e.get("start_time") or 0)
    ages.append(age)
    if e.get("end_time") and age<=30:
      try:
        with urllib.request.urlopen(f"http://127.0.0.1:5000/api/events/{e['id']}/clip.mp4",timeout=12) as r:
          n=len(r.read(2048))
        if n>500:
          print(f"YOUNG age={age:.0f} peek={n}")
          raise SystemExit(0)
      except Exception as ex:
        print(f"age={age:.0f} clip {ex}")
  print(f"wait {i} ages={[round(a) for a in ages[:3]]}")
  time.sleep(3)
print("NO_YOUNG")
raise SystemExit(1)
PY
