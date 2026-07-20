#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

echo "=== wait postgres+minio ==="
for i in $(seq 1 60); do
  pg_ok=0; mi_ok=0
  docker exec citevision-v2-postgres pg_isready -U citevision >/dev/null 2>&1 && pg_ok=1
  docker exec citevision-v2-minio curl -sf http://127.0.0.1:9000/minio/health/live >/dev/null 2>&1 && mi_ok=1 \
    || docker exec citevision-v2-minio ls /data >/dev/null 2>&1 && mi_ok=1
  if [ "$pg_ok" = 1 ] && [ "$mi_ok" = 1 ]; then
    echo "ready after ${i}s"
    break
  fi
  echo "wait $i pg=$pg_ok minio=$mi_ok"
  sleep 2
done
docker exec citevision-v2-postgres pg_isready -U citevision

# Ensure backend briefly for optional API purge — not required; purge script handles DB+minio directly
export ADMIN_PASSWORD='Hologram2026!'
export REENABLE_DEMO_RULES=0
sed -i 's/\r$//' /mnt/c/Users/gheno/citevision/scripts/purge_all_evidence_clean_slate.sh
cp -f /mnt/c/Users/gheno/citevision/scripts/purge_all_evidence_clean_slate.sh "$ROOT/scripts/"
bash "$ROOT/scripts/purge_all_evidence_clean_slate.sh"

echo "=== verify empty ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT 'alerts', count(*) FROM alerts UNION ALL SELECT 'events', count(*) FROM events;"
docker exec citevision-v2-minio du -sh /data/citevision-evidence 2>/dev/null || echo "minio_evidence=?"
echo "PURGE_DONE"
