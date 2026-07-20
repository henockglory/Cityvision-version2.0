#!/usr/bin/env bash
set -uo pipefail
echo "=== .env VIDEOS ==="
grep VIDEOS /home/gheno/citevision-v2/.env || true
echo "=== candidate dirs ==="
for d in \
  /home/gheno/citevision-v2/data/videos \
  /home/gheno/citevision-v2/infra/data/videos \
  /mnt/c/Users/gheno/citevision/data/videos \
  /mnt/c/Users/gheno/citevision/infra/data/videos \
  /mnt/c/Citevision/data/videos
do
  if [ -d "$d" ]; then
    echo "DIR $d"
    find "$d" -name '*_stream.mp4' 2>/dev/null | head -10
    du -sh "$d" 2>/dev/null
  else
    echo "MISS $d"
  fi
done
echo "=== DB paths ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT id::text, left(local_stream_path,120), go2rtc_src FROM org_demo_videos WHERE status='ready';"
echo "=== go2rtc mounts ==="
docker inspect citevision-v2-go2rtc --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'
