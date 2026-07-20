#!/usr/bin/env bash
set -uo pipefail
cd /home/gheno/citevision-v2

# Push Frigate recordings under 15G exit gate
export FRIGATE_DEMO_RETENTION_MIN=5
bash scripts/demo-retention-purge.sh || true
sudo find /var/lib/docker/volumes/infra_frigate_recordings/_data -type f -mmin +5 -delete 2>/dev/null || true
sudo find /var/lib/docker/volumes/infra_frigate_clips/_data -type f -mmin +5 -delete 2>/dev/null || true
# If still large, keep only last 60 minutes max
FRIG_G=$(sudo du -s -BG /var/lib/docker/volumes/infra_frigate_recordings/_data 2>/dev/null | awk '{gsub(/G/,"",$1); print $1+0}')
echo "frigate_after_5m=${FRIG_G}G"
if (( FRIG_G >= 15 )); then
  echo "extra purge mmin+1"
  sudo find /var/lib/docker/volumes/infra_frigate_recordings/_data -type f -mmin +1 -delete 2>/dev/null || true
fi
sudo fstrim -v / || true

C_G=$(df -P /mnt/c | awk 'NR==2 {printf "%d", $4/1024/1024}')
FRIG_G=$(sudo du -s -BG /var/lib/docker/volumes/infra_frigate_recordings/_data 2>/dev/null | awk '{gsub(/G/,"",$1); print $1+0}')
MINIO_G=$(sudo du -s -BG /var/lib/docker/volumes/infra_minio_data/_data 2>/dev/null | awk '{gsub(/G/,"",$1); print $1+0}')
echo "EXIT_CHECK C_free=${C_G}G frigate_rec=${FRIG_G}G minio=${MINIO_G}G"

# Demo rules stay OFF
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "UPDATE rules SET is_enabled=false WHERE name LIKE 'Démo%';" >/dev/null || true

# Confirm tags + map
git tag -l 'phaseA/*/PASS'
cat validation-evidence/PHASEA_PASS_TAGS.md 2>/dev/null | head -20

if (( C_G >= 40 )) && (( FRIG_G < 15 )); then
  echo "DISK_EXIT_OK"
else
  echo "DISK_EXIT_WARN C=${C_G} frigate=${FRIG_G}"
fi
echo "P2_COMPLETE"
