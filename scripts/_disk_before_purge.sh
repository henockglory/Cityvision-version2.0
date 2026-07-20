#!/usr/bin/env bash
set -uo pipefail
echo "=== BEFORE sizes ==="
df -h / /mnt/c
echo "--- volumes ---"
sudo du -sh /var/lib/docker/volumes/infra_frigate_recordings \
  /var/lib/docker/volumes/infra_minio_data \
  /var/lib/docker/volumes/infra_frigate_clips \
  /home/gheno/citevision-v2/validation-evidence 2>/dev/null || true
echo "--- minio ---"
docker exec citevision-v2-minio du -sh /data /data/citevision-evidence 2>/dev/null || echo "minio down"
echo "--- vhdx (from windows later) ---"
