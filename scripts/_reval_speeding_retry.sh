#!/usr/bin/env bash
set -uo pipefail
cd /home/gheno/citevision-v2
KEY=$(python3 - <<'PY'
from pathlib import Path
for line in Path(".env").read_text().splitlines():
    if line.strip().startswith("INTERNAL_API_KEY="):
        print(line.split("=",1)[1].strip().strip('"').strip("'")); break
PY
)
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild" -H "X-Internal-Key: $KEY" || true
# Restart frigate to pick up go2rtc RTSP paths now that videos mount is fixed
docker restart citevision-v2-frigate
for i in $(seq 1 40); do
  curl -sf http://127.0.0.1:5000/api/version >/dev/null && break
  sleep 3
done
# Wait for recordings to appear for speed cam
for i in $(seq 1 20); do
  n=$(find /var/lib/docker/volumes/infra_frigate_recordings/_data -type f 2>/dev/null | wc -l)
  echo "rec_files=$n"
  (( n > 5 )) && break
  sleep 5
done
bash scripts/ensure-demo-streams.sh || true
curl -sf http://127.0.0.1:1984/api/streams >/dev/null && echo go2rtc_ok
bash /home/gheno/citevision-v2/scripts/_reval_one_alias.sh speeding; echo EXIT:$?
