#!/usr/bin/env bash
# Normalize demo video paths in Postgres to WSL ext4 (never /mnt/c/...).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

CANONICAL="$ROOT/data/videos"
DEMO_ORG="${DEMO_ORG_ID:-e312f375-7442-4089-8022-ed232abc09e8}"

echo "=== fix-demo-camera-paths ==="
echo "ROOT=$ROOT"
echo "CANONICAL=$CANONICAL"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "[FAIL] DATABASE_URL not set in $ENV_FILE"
  exit 1
fi

mkdir -p "$CANONICAL/demo/$DEMO_ORG"

export ROOT="$ROOT"
export CANONICAL="$CANONICAL"
export DEMO_ORG="$DEMO_ORG"

python3 - <<PY
import json, os, re, subprocess, sys

root = os.environ["ROOT"]
canonical = os.environ["CANONICAL"]
demo_org = os.environ["DEMO_ORG"]
db_url = os.environ["DATABASE_URL"]

def psql(sql):
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        raise SystemExit(1)
    return r.stdout.strip()

def psql_exec(sql):
    subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", sql],
        check=True,
    )

def normalize_path(path: str, video_id: str | None) -> str | None:
    if not path:
        return None
    path = path.replace(chr(92), "/")
    # Already canonical WSL path under data/videos
    if path.startswith(canonical):
        return path if os.path.isfile(path) else None
    # Windows C:\Citevision\... or /mnt/c/Citevision/...
    m = re.search(r"demo/([0-9a-f-]{36})/([^/]+_stream\.mp4)", path, re.I)
    if m:
        org, fname = m.group(1), m.group(2)
        candidate = os.path.join(canonical, "demo", org, fname)
        if os.path.isfile(candidate):
            return candidate
    if video_id:
        # Try org_demo_videos pattern
        rows = psql(
            f"SELECT local_stream_path, go2rtc_src FROM org_demo_videos WHERE id::text LIKE '{video_id[:8]}%';"
        )
        if rows:
            parts = rows.split("|")
            for p in parts:
                if p and os.path.isfile(p.replace("/mnt/c/Citevision", "/mnt/c/Citevision")):
                    pass
        # glob by video id prefix in filename
        demo_dir = os.path.join(canonical, "demo", demo_org)
        if os.path.isdir(demo_dir):
            for fn in os.listdir(demo_dir):
                if video_id[:8] in fn and fn.endswith("_stream.mp4"):
                    return os.path.join(demo_dir, fn)
    # Last resort: scan demo dir
    demo_dir = os.path.join(canonical, "demo", demo_org)
    if os.path.isdir(demo_dir):
        base = os.path.basename(path)
        if base and os.path.isfile(os.path.join(demo_dir, base)):
            return os.path.join(demo_dir, base)
    return None

fixed_cams = 0
fixed_vids = 0

# Fix org_demo_videos.local_stream_path
rows = psql("SELECT id::text, name, local_stream_path FROM org_demo_videos ORDER BY name;")
for line in rows.splitlines():
    if not line.strip():
        continue
    vid, name, path = line.split("|", 2)
    new = normalize_path(path, vid)
    if not new:
        demo_dir = os.path.join(canonical, "demo", demo_org)
        if os.path.isdir(demo_dir):
            for fn in os.listdir(demo_dir):
                if vid[:8] in fn and fn.endswith("_stream.mp4"):
                    new = os.path.join(demo_dir, fn)
                    break
    if new and new != path:
        esc = new.replace("'", "''")
        psql_exec(f"UPDATE org_demo_videos SET local_stream_path = '{esc}' WHERE id = '{vid}'::uuid;")
        print(f"[FIX] video {name}: {path} -> {new}")
        fixed_vids += 1
    elif new:
        print(f"[OK] video {name}: {new}")

# Fix cameras.metadata.video_file for demo virtual cameras
rows = psql(
    "SELECT id::text, name, metadata::text FROM cameras WHERE metadata->>'demo' = 'true' OR metadata->>'virtual' = 'true';"
)
for line in rows.splitlines():
    if not line.strip():
        continue
    parts = line.split("|", 2)
    if len(parts) < 3:
        continue
    cam_id, name, meta_raw = parts[0], parts[1], parts[2]
    meta = json.loads(meta_raw)
    vf = meta.get("video_file") or ""
    demo_vid = meta.get("demo_video_id") or ""
    new = normalize_path(vf, demo_vid) if vf else None
    if not new and demo_vid:
        demo_dir = os.path.join(canonical, "demo", demo_org)
        if os.path.isdir(demo_dir):
            for fn in os.listdir(demo_dir):
                if demo_vid[:8] in fn and fn.endswith("_stream.mp4"):
                    new = os.path.join(demo_dir, fn)
                    break
    if new and new != vf:
        meta["video_file"] = new
        esc = json.dumps(meta).replace("'", "''")
        psql_exec(f"UPDATE cameras SET metadata = '{esc}'::jsonb WHERE id = '{cam_id}'::uuid;")
        print(f"[FIX] camera {name}: video_file -> {new}")
        fixed_cams += 1
    elif new or vf:
        print(f"[OK] camera {name}: {(new or vf)[:80]}")

# Ensure demo cameras active
psql_exec("UPDATE cameras SET is_active = TRUE WHERE metadata->>'demo' = 'true';")

print(f"=== done: {fixed_vids} videos, {fixed_cams} cameras fixed ===")
PY

echo "[OK] fix-demo-camera-paths complete"
