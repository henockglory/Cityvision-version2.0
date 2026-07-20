#!/usr/bin/env bash
set -uo pipefail
cd ~/citevision-v2
# shellcheck disable=SC1091
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$PWD")"
load_dotenv "$ENV_FILE"

USER="${POSTGRES_USER:-citevision}"
PASS="${POSTGRES_PASSWORD:-changeme_postgres}"
DB="${POSTGRES_DB:-citevision}"
PORT="${POSTGRES_PORT:-5433}"

run_sql() {
  PGPASSWORD="$PASS" docker exec -i "$(docker ps --format '{{.Names}}' | grep -E 'postgres|citevision.*db' | head -1)" \
    psql -U "$USER" -d "$DB" -v ON_ERROR_STOP=0 "$@" 2>/dev/null \
  || PGPASSWORD="$PASS" psql -h 127.0.0.1 -p "$PORT" -U "$USER" -d "$DB" "$@" 2>/dev/null
}

# find postgres container
echo "=== docker postgres ==="
docker ps --format '{{.Names}} {{.Ports}}' | grep -iE 'postgres|5432|5433' || true
PC=$(docker ps --format '{{.Names}}' | grep -iE 'postgres|citevision.*db' | head -1 || true)
echo "PC=$PC"

if [[ -n "$PC" ]]; then
  docker exec -i "$PC" psql -U "$USER" -d "$DB" <<'SQL'
\echo === cameras ===
SELECT id::text, name, host(host)::text AS host, is_active,
       COALESCE(metadata->>'demo','') AS demo,
       COALESCE(metadata->>'go2rtc_src','') AS go2rtc,
       COALESCE(metadata->>'demo_video_id','') AS video_id,
       COALESCE(metadata->>'frigate_exclude','') AS excl
FROM cameras ORDER BY name;

\echo === zones lines ===
SELECT c.name, count(DISTINCT z.id) AS zones, count(DISTINCT l.id) AS lines
FROM cameras c
LEFT JOIN zones z ON z.camera_id = c.id
LEFT JOIN lines l ON l.camera_id = c.id
GROUP BY c.name ORDER BY c.name;

\echo === org_demo_videos ===
SELECT id::text, title, duration_sec, file_path, created_at
FROM org_demo_videos ORDER BY created_at DESC LIMIT 20;

\echo === red_light events sample meta keys ===
SELECT id::text, created_at,
       COALESCE(metadata->>'evidence_abort_reason', metadata->>'abort_reason', '') AS abort,
       COALESCE(metadata->>'capture_source','') AS src,
       left(metadata::text, 200) AS meta_prefix
FROM events
WHERE event_type = 'red_light_violation'
ORDER BY created_at DESC LIMIT 5;

\echo === red_light count ===
SELECT count(*) FROM events WHERE event_type = 'red_light_violation';

\echo === alerts complete last 50 ===
SELECT count(*) FILTER (WHERE evidence_snapshot IS NOT NULL) AS with_snap,
       count(*) AS total
FROM (
  SELECT evidence_snapshot FROM alerts ORDER BY created_at DESC LIMIT 50
) t;

\echo === alert titles recent ===
SELECT created_at, title, severity,
       left(coalesce(evidence_snapshot::text,''), 120) AS snap
FROM alerts ORDER BY created_at DESC LIMIT 15;
SQL
fi

echo
echo "=== ffprobe red_light demo video aaea7c30 ==="
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 \
  data/videos/demo/74d51ead-97a7-4e41-a488-503a9b90c466/aaea7c30-1c4c-4ce5-9cd6-4b1f8ded4118_stream.mp4

echo
echo "=== go2rtc / demo ingest loop start from logs ==="
grep -a 'aaea7c30\|demo ingest via go2rtc\|stream ready' logs/backend.log 2>/dev/null | grep -a 'aaea7c30\|demo:' | tail -20
grep -a 'aaea7c30' logs/ai-engine.log 2>/dev/null | tail -10

echo
echo "=== Windows vs WSL script counts ==="
echo "WSL fix: $(ls scripts/_fix_* 2>/dev/null | wc -l) diag: $(ls scripts/_diag_* 2>/dev/null | wc -l)"
echo "Win fix: $(ls /mnt/c/Users/gheno/citevision/scripts/_fix_* 2>/dev/null | wc -l) diag: $(ls /mnt/c/Users/gheno/citevision/scripts/_diag_* 2>/dev/null | wc -l)"
# broader: all _fix in name anywhere under scripts
echo "WSL scripts matching _fix_: $(find scripts -name '*_fix_*' 2>/dev/null | wc -l)"
echo "WSL scripts matching _diag_: $(find scripts -name '*_diag_*' 2>/dev/null | wc -l)"
echo "Win scripts matching _fix_: $(find /mnt/c/Users/gheno/citevision/scripts -name '*_fix_*' 2>/dev/null | wc -l)"
echo "Win scripts matching _diag_: $(find /mnt/c/Users/gheno/citevision/scripts -name '*_diag_*' 2>/dev/null | wc -l)"

echo
echo "=== rebuild status codes last 7d ==="
python3 - <<'PY'
from pathlib import Path
from datetime import datetime, timedelta
import re, collections
log=Path("logs/backend.log")
text=log.read_bytes().decode("utf-8","replace")
cutoff=datetime.now().astimezone()-timedelta(days=7)
codes=collections.Counter()
rebuild_req=0
reload_fail=0
rebuild_ok_msg=0
for line in text.splitlines():
  m=re.search(r'"time":"([^"]+)"', line)
  if not m: continue
  try: ts=datetime.fromisoformat(m.group(1))
  except Exception: continue
  if ts < cutoff: continue
  if 'frigate/rebuild' in line and '"method":"POST"' in line:
    rebuild_req += 1
    cm=re.search(r'"status":(\d+)', line)
    if cm: codes[cm.group(1)] += 1
  if 'frigate config rebuilt' in line:
    rebuild_ok_msg += 1
  if 'frigate reload failed' in line:
    reload_fail += 1
print("POST /frigate/rebuild requests:", rebuild_req, "by status:", dict(codes))
print("config rebuilt msgs:", rebuild_ok_msg, "reload failed msgs:", reload_fail)
print("502 rate among rebuild HTTP:", round(100*codes.get('502',0)/max(rebuild_req,1),1), "%")
PY
