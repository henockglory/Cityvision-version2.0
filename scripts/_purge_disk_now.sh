#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

echo "=== start dockerd ==="
bash scripts/_start_dockerd_wsl.sh 2>/dev/null || true
for i in $(seq 1 60); do
  if docker info >/dev/null 2>&1; then echo "docker_ok $i"; break; fi
  sleep 2
done
docker info >/dev/null || { echo "DOCKER_FAIL"; exit 1; }

# Bring core containers up
cd infra 2>/dev/null || true
docker start citevision-v2-postgres citevision-v2-minio citevision-v2-redis citevision-v2-mosquitto 2>/dev/null || true
cd "$ROOT"

for i in $(seq 1 45); do
  docker exec citevision-v2-postgres pg_isready -U citevision >/dev/null 2>&1 \
    && docker exec citevision-v2-minio ls /data >/dev/null 2>&1 && { echo "pg+minio ready"; break; }
  sleep 2
done

echo "=== AVANT ==="
df -h / | head -2
docker exec citevision-v2-minio du -sh /data /data/citevision-evidence 2>/dev/null || true
sudo du -sh /var/lib/docker/volumes/infra_frigate_recordings /var/lib/docker/volumes/infra_minio_data /var/lib/docker/volumes/infra_frigate_clips 2>/dev/null || true

echo "=== Stop AI/backend to free locks ==="
pkill -f citevision-ai 2>/dev/null || true
pkill -f citevision-api 2>/dev/null || true
pkill -f rules-engine 2>/dev/null || true
sleep 2

echo "=== TRUNCATE DB ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -v ON_ERROR_STOP=1 -c "TRUNCATE TABLE alerts RESTART IDENTITY CASCADE;"
docker exec citevision-v2-postgres psql -U citevision -d citevision -v ON_ERROR_STOP=1 -c "TRUNCATE TABLE events RESTART IDENTITY CASCADE;"
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "TRUNCATE TABLE evidence_objects RESTART IDENTITY CASCADE;" 2>/dev/null || true
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "UPDATE rule_counters SET count=0, last_event_type='', updated_at=NOW();" 2>/dev/null || true
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "VACUUM ANALYZE alerts; VACUUM ANALYZE events;"

echo "=== Purge MinIO evidence ==="
docker exec citevision-v2-minio sh -c 'rm -rf /data/citevision-evidence && mkdir -p /data/citevision-evidence && du -sh /data/citevision-evidence'

echo "=== Purge Frigate recordings (~203G) ==="
docker run --rm -v infra_frigate_recordings:/v alpine sh -c 'rm -rf /v/*; echo frigate_recordings cleared; du -sh /v'
echo "=== Purge Frigate clips ==="
docker run --rm -v infra_frigate_clips:/v alpine sh -c 'rm -rf /v/*; echo frigate_clips cleared; du -sh /v' 2>/dev/null \
  || docker run --rm -v infra_frigate_clips:/v alpine sh -c 'rm -rf /v/*; echo cleared' 2>/dev/null || true

# Also clear frigate cache / exports if present
for vol in infra_frigate_cache infra_frigate_exports; do
  docker run --rm -v ${vol}:/v alpine sh -c "rm -rf /v/*; echo ${vol} cleared" 2>/dev/null || true
done

echo "=== Purge clips locaux + validation-evidence ==="
rm -rf "$ROOT/backend/data/clips"/* 2>/dev/null || true
mkdir -p "$ROOT/backend/data/clips"
# Keep PASS map file if any, wipe rest of validation-evidence
find "$ROOT/validation-evidence" -mindepth 1 -maxdepth 1 -type d -exec rm -rf {} + 2>/dev/null || true
# Windows clips
rm -rf /mnt/c/Users/gheno/citevision/backend/data/clips/* 2>/dev/null || true

echo "=== Disable demo rules (éviter re-remplissage) ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "UPDATE rules SET is_enabled=false, updated_at=NOW() WHERE name LIKE 'Démo%';" || true

echo "=== docker image prune ==="
docker image prune -af || true

echo "=== APRÈS logique ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT 'alerts', count(*) FROM alerts UNION ALL SELECT 'events', count(*) FROM events;"
docker exec citevision-v2-minio du -sh /data/citevision-evidence
sudo du -sh /var/lib/docker/volumes/infra_frigate_recordings /var/lib/docker/volumes/infra_minio_data /var/lib/docker/volumes/infra_frigate_clips 2>/dev/null || true

echo "=== fstrim ==="
sudo fstrim -av 2>/dev/null || sudo fstrim -v / || true
sync
df -h / /mnt/c | head -5
echo "PURGE_DONE — ready for _compact_now.ps1 (admin)"
