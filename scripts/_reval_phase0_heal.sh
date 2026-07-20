#!/usr/bin/env bash
# Phase 0 — disk budget + heal stack for Phase A revalidation.
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
export PATH="/usr/local/go/bin:$PATH"
export HOME=/home/gheno

echo "=== DISK BUDGET ==="
df -h / /mnt/c | head -5
sudo du -sh /var/lib/docker/volumes/infra_frigate_recordings \
  /var/lib/docker/volumes/infra_minio_data \
  /var/lib/docker/volumes/infra_frigate_clips 2>/dev/null || true

# Sync retention + health from Windows edit tree
WIN=/mnt/c/Users/gheno/citevision
for f in infra/frigate.base.yaml scripts/health_check_all.sh; do
  if [ -f "$WIN/$f" ]; then
    mkdir -p "$(dirname "$ROOT/$f")"
    cp "$WIN/$f" "$ROOT/$f"
    sed -i 's/\r$//' "$ROOT/$f"
  fi
done
# Live Frigate config retain (mounted volume) — patch in place
if [ -f "$ROOT/infra/frigate-config/config.yml" ]; then
  cp "$WIN/infra/frigate-config/config.yml" "$ROOT/infra/frigate-config/config.yml" 2>/dev/null || true
  sed -i 's/\r$//' "$ROOT/infra/frigate-config/config.yml" 2>/dev/null || true
fi

echo "=== start dockerd + core containers ==="
bash scripts/_start_dockerd_wsl.sh 2>/dev/null || true
for i in $(seq 1 40); do
  docker info >/dev/null 2>&1 && break
  sleep 2
done
docker info >/dev/null || { echo DOCKER_FAIL; exit 1; }

# compose up if needed
if [ -f infra/docker-compose.yml ]; then
  (cd infra && docker compose up -d postgres redis mosquitto minio mailhog go2rtc frigate 2>/dev/null) || true
fi
docker start citevision-v2-postgres citevision-v2-redis citevision-v2-mosquitto \
  citevision-v2-minio citevision-v2-mailhog citevision-v2-go2rtc citevision-v2-frigate 2>/dev/null || true

for i in $(seq 1 45); do
  curl -sf http://127.0.0.1:5000/api/version >/dev/null 2>&1 \
    && docker exec citevision-v2-postgres pg_isready -U citevision >/dev/null 2>&1 \
    && break
  sleep 2
done

# DEMO_RETENTION in .env
if ! grep -q '^DEMO_RETENTION_MINUTES=' .env 2>/dev/null; then
  echo 'DEMO_RETENTION_MINUTES=60' >> .env
fi
if ! grep -q '^FRIGATE_DEMO_RETENTION_MIN=' .env 2>/dev/null; then
  echo 'FRIGATE_DEMO_RETENTION_MIN=30' >> .env
fi

echo "=== restart backend / AI / rules / vite ==="
python3 scripts/_restart_backend.py || true
python3 scripts/_restart_ai.py || true
bash scripts/_task5_rules_up.sh 2>/dev/null || {
  if ! curl -sf http://127.0.0.1:8010/health >/dev/null; then
    set -a; source .env; set +a
    setsid nohup ./rules-engine/bin/rules-engine >> logs/rules-engine.log 2>&1 &
    echo $! > logs/rules-engine.pid
    sleep 2
  fi
}
if ! curl -sf http://127.0.0.1:5174/ >/dev/null 2>&1; then
  (cd frontend && setsid nohup npm run dev -- --host 127.0.0.1 --port 5174 >> ../logs/vite.log 2>&1 & echo $! > ../logs/vite.pid)
  sleep 5
fi

echo "=== soft Frigate rebuild (retain patch) ==="
KEY=$(python3 - <<'PY'
from pathlib import Path
for line in Path("/home/gheno/citevision-v2/.env").read_text().splitlines():
    if line.strip().startswith("INTERNAL_API_KEY="):
        print(line.split("=",1)[1].strip().strip('"').strip("'")); break
PY
)
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild" \
  -H "X-Internal-Key: ${KEY}" || echo "rebuild_warn"

echo "=== all Demo rules OFF ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "UPDATE rules SET is_enabled=false, updated_at=NOW() WHERE name LIKE 'Démo%';" || true

echo "=== health_check_all ==="
bash scripts/health_check_all.sh
echo "PHASE0_DONE"
