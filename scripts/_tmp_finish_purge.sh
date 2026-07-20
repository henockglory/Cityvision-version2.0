#!/usr/bin/env bash
set -uo pipefail
docker run --rm -v infra_frigate_clips:/v alpine sh -c 'rm -rf /v/*; du -sh /v; echo clips_cleared'
docker exec citevision-v2-minio sh -c 'du -sh /data/* 2>/dev/null; ls -la /data'
echo "=== volumes ==="
sudo du -sh /var/lib/docker/volumes/infra_frigate_recordings \
  /var/lib/docker/volumes/infra_frigate_clips \
  /var/lib/docker/volumes/infra_minio_data 2>/dev/null
echo "=== vhdx ==="
ls -lh /mnt/c/Users/gheno/AppData/Local/wsl/*/ext4.vhdx
df -h / /mnt/c | head -3
