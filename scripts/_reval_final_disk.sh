#!/usr/bin/env bash
set -uo pipefail
FRIGATE_DEMO_RETENTION_MIN=5 bash /home/gheno/citevision-v2/scripts/demo-retention-purge.sh || true
sudo find /var/lib/docker/volumes/infra_frigate_recordings/_data -type f -mmin +5 -delete 2>/dev/null || true
sudo fstrim -v / || true
echo -n "frigate_rec="; sudo du -s -BG /var/lib/docker/volumes/infra_frigate_recordings/_data 2>/dev/null | awk '{print $1}'
df -P /mnt/c | awk 'NR==2 {printf "C_free_GB=%d\n", $4/1024/1024}'
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "UPDATE rules SET is_enabled=false WHERE name LIKE 'Démo%'; SELECT count(*) FROM rules WHERE name LIKE 'Démo%' AND is_enabled;"
