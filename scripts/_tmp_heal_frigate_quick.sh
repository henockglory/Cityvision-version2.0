#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

bash "$ROOT/scripts/ensure-demo-streams.sh" || true
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams; echo
docker restart citevision-v2-go2rtc
sleep 4
docker restart citevision-v2-frigate
for i in $(seq 1 40); do
  curl -sf --max-time 3 http://127.0.0.1:5000/api/version >/dev/null && break
  sleep 2
done
bash "$ROOT/scripts/ensure-demo-streams.sh" || true
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams; echo

python3 - <<'PY'
import json,time,urllib.request
fc="cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"
for i in range(50):
  try:
    ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=5",timeout=10).read())
  except Exception as e:
    print("err",e); time.sleep(3); continue
  now=time.time()
  ages=[round(now-float(e.get("start_time") or 0)) for e in (ev or [])[:3]]
  for e in (ev or []):
    age=now-float(e.get("start_time") or 0)
    if age<=90:
      print(f"YOUNG age={age:.0f}s"); raise SystemExit(0)
  print(f"wait {i} ages={ages}")
  time.sleep(3)
print("NO_YOUNG"); raise SystemExit(1)
PY
