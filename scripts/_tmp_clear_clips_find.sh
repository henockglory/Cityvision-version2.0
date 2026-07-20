#!/usr/bin/env bash
set -uo pipefail
echo "=== clear frigate clips via find ==="
docker run --rm -v infra_frigate_clips:/v alpine sh -c '
  find /v -mindepth 1 -delete 2>/dev/null || true
  du -sh /v
  echo clips_ok
'
# also wipe leftover frigate recordings growth
docker run --rm -v infra_frigate_recordings:/v alpine sh -c '
  find /v -mindepth 1 -delete 2>/dev/null || true
  du -sh /v
  echo recordings_ok
'
sudo fstrim -v / || true
sync
echo "=== final sizes ==="
sudo du -sh /var/lib/docker/volumes/infra_frigate_recordings \
  /var/lib/docker/volumes/infra_frigate_clips \
  /var/lib/docker/volumes/infra_minio_data 2>/dev/null
df -h / | head -2
ls -lh /mnt/c/Users/gheno/AppData/Local/wsl/*/ext4.vhdx
