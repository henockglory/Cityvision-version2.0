#!/usr/bin/env bash
set -uo pipefail
cd ~/citevision-v2
# shellcheck disable=SC1091
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$PWD")"
load_dotenv "$ENV_FILE"

echo "=== cameras DB ==="
python3 - <<'PY'
import os, json
try:
    import psycopg2
except ImportError:
    import subprocess, sys
    print("no psycopg2, trying docker/psql")
    sys.exit(0)

url = os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_URL")
if not url:
    user=os.environ.get("POSTGRES_USER","citevision")
    pw=os.environ.get("POSTGRES_PASSWORD","changeme_postgres")
    db=os.environ.get("POSTGRES_DB","citevision")
    host=os.environ.get("POSTGRES_HOST","127.0.0.1")
    port=os.environ.get("POSTGRES_PORT","5433")
    url=f"postgresql://{user}:{pw}@{host}:{port}/{db}"
conn=psycopg2.connect(url)
cur=conn.cursor()
cur.execute("SELECT count(*) FROM cameras")
print("cameras_total", cur.fetchone()[0])
cur.execute("SELECT count(*) FROM cameras WHERE is_active")
print("cameras_active", cur.fetchone()[0])
cur.execute("""
SELECT id::text, name, host(host)::text, is_active, metadata->>'demo' as demo,
       metadata->>'go2rtc_src' as go2rtc, metadata->>'frigate_exclude' as excl
FROM cameras ORDER BY name
""")
for row in cur.fetchall():
    print("CAM", row)
cur.execute("""
SELECT c.id::text, c.name, count(z.id) as zones, count(l.id) as lines
FROM cameras c
LEFT JOIN zones z ON z.camera_id=c.id
LEFT JOIN lines l ON l.camera_id=c.id
GROUP BY c.id, c.name ORDER BY c.name
""")
print("--- zones/lines ---")
for row in cur.fetchall():
    print(row)
conn.close()
PY

# Fallback psql via docker
if ! python3 -c 'import psycopg2' 2>/dev/null; then
  PGPASSWORD="${POSTGRES_PASSWORD:-changeme_postgres}" psql -h 127.0.0.1 -p "${POSTGRES_PORT:-5433}" -U "${POSTGRES_USER:-citevision}" -d "${POSTGRES_DB:-citevision}" -c \
    "SELECT id, name, host(host), is_active, metadata->>'demo' FROM cameras ORDER BY name;" 2>&1 | head -40
fi
