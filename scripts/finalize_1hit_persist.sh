#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
cp /mnt/c/Users/gheno/citevision-v2/backend/cmd/seed-demo-spatial/main.go backend/cmd/seed-demo-spatial/main.go
cp /mnt/c/Users/gheno/citevision-v2/backend/cmd/seed-demo-rules/main.go backend/cmd/seed-demo-rules/main.go
cp /mnt/c/Users/gheno/citevision-v2/scripts/watch-backend.sh scripts/watch-backend.sh
cp /mnt/c/Users/gheno/citevision-v2/scripts/push_ai_spatial_from_api.py scripts/push_ai_spatial_from_api.py
cp /mnt/c/Users/gheno/citevision-v2/scripts/validate_demo_1hit_seven.py scripts/
sed -i 's/\r$//' scripts/watch-backend.sh backend/cmd/seed-demo-*/main.go scripts/*.py 2>/dev/null || true

set -a; . ./.env; set +a
export DEMO_RULES_ENABLED=0
bash scripts/seed-demo-spatial.sh
bash scripts/seed-demo-rules.sh

docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "UPDATE rules SET is_enabled=false, updated_at=NOW() WHERE name LIKE 'Démo%'; SELECT name, is_enabled FROM rules WHERE name LIKE 'Démo%' ORDER BY name;"

# Restart watch-backend with IPv4 probe fix
if [[ -f logs/watch-backend.pid ]]; then kill "$(cat logs/watch-backend.pid)" 2>/dev/null || true; fi
nohup bash scripts/watch-backend.sh >>logs/watch-backend.log 2>&1 &
echo $! > logs/watch-backend.pid
echo "watch-backend pid=$(cat logs/watch-backend.pid)"
curl -sf http://127.0.0.1:8081/health; echo
