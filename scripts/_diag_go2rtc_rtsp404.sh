#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

echo "=== go2rtc container ==="
docker inspect citevision-v2-go2rtc --format 'Status={{.State.Status}} Ports={{json .NetworkSettings.Ports}}'
docker inspect citevision-v2-go2rtc --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'

echo "=== go2rtc logs (tail) ==="
docker logs citevision-v2-go2rtc --tail 40 2>&1

echo "=== streams API detail ==="
curl -sS http://127.0.0.1:1984/api/streams | python3 -m json.tool | head -80

echo "=== video files exist? ==="
ls -la "$ROOT/data/videos/demo/74d51ead-97a7-4e41-a488-503a9b90c466/" 2>/dev/null | head -20 || echo missing_dir
docker exec citevision-v2-go2rtc ls -la /videos/demo/74d51ead-97a7-4e41-a488-503a9b90c466/ 2>&1 | head -20

echo "=== go2rtc config ==="
docker exec citevision-v2-go2rtc cat /config/go2rtc.yaml 2>/dev/null | head -60 || true
ls "$ROOT/infra/go2rtc"* 2>/dev/null || true
find "$ROOT/infra" -name '*go2rtc*' 2>/dev/null | head

echo "=== listen ports inside container ==="
docker exec citevision-v2-go2rtc sh -c 'netstat -tlnp 2>/dev/null || ss -tlnp' 2>&1 | head -30

echo "=== try API stream info ==="
curl -sS "http://127.0.0.1:1984/api/streams?src=demo-74d51ead-aaea7c30" | head -c 500; echo
