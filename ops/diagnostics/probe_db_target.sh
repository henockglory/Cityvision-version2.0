#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh 2>/dev/null || true
ENV_FILE="$ROOT/.env"
echo "=== DATABASE from .env ==="
grep -E '^(DATABASE_URL|POSTGRES|DB_)' "$ENV_FILE" 2>/dev/null | sed 's/:[^:@]*@/:***@/' || true
echo "=== which postgres ports ==="
ss -ltnp 2>/dev/null | grep -E '5432|5433' || netstat -ltn 2>/dev/null | grep 5432 || true
echo "=== all schemas/tables in citevision db ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' ORDER BY 1;"
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT schemaname, tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') LIMIT 40;"
echo "=== try public.cameras ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT count(*) FROM cameras;" 2>&1 || true
echo "=== backend migrate log ==="
grep -iE 'migrat|schema|postgres|database|FATAL|error' "$ROOT/logs/backend.log" | head -40
echo "=== PATH go ==="
export PATH="$PATH:/usr/local/go/bin:$HOME/go/bin"
which go; go version
