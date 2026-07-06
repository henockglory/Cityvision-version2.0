#!/usr/bin/env bash
# Restore demo workspace after accidental "Reset démo" (videos + virtual cameras + zone links).
# Keeps existing zones/lines/rules; rehydrates org_demo_videos from C:\Citevision backup.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

ORG="${DEMO_ORG_ID:-e312f375-7442-4089-8022-ed232abc09e8}"
EMAIL="${ADMIN_EMAIL:-glory.henock@hologram.cd}"
PASS="${ADMIN_PASSWORD:-Hologram2026!}"
API="${BACKEND_API_URL:-http://localhost:8081}"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Restauration démo Kinshasa (après reset accidentel)      ║"
echo "╚══════════════════════════════════════════════════════════╝"

echo "==> 1/7 Copie des vidéos depuis C:\\Citevision"
bash "$ROOT/scripts/restore-demo-videos-from-citevision.sh" "$ORG" || {
  echo "[WARN] restore-demo-videos-from-citevision failed — continuing if files exist locally"
}

echo "==> 2/7 Réhydratation DB (videos + caméras virtuelles + zones/lignes)"
RESTORE_ROOT="$ROOT" python3 <<PY
import json, os, subprocess, sys
from pathlib import Path

ROOT = Path(os.environ["RESTORE_ROOT"]).resolve()
ORG = "${ORG}"
VIDEOS_DIR = ROOT / "data/videos/demo" / ORG

# Known mapping (camera UUID stable + video file from backup)
SPECS = [
    {
        "video_id": "d4cadc04-f940-497d-8031-80418ac7dd86",
        "camera_id": "726ff8a1-8442-4bdb-96ad-ec40a2fbb424",
        "name": "Feux",
        "zones": ["Zone_des_feux", "Zone_Observation"],
        "lines": [],
    },
    {
        "video_id": "eb1d2b8e-6c8d-47c5-82fa-e3c24f0425e5",
        "camera_id": "01ee632c-271c-4e66-ba98-3d1d7e430c09",
        "name": "Ligne Continue",
        "zones": ["Zone_distance_parcourue"],
        "lines": [],
    },
    {
        "video_id": "50bcc479-392a-4051-aff7-dfa4fab50f0f",
        "camera_id": "bbf2c5ae-2650-4fc8-b528-2a014e79df87",
        "name": "Décompte des voitures",
        "zones": [],
        "lines": ["Ligne_count"],
    },
    {
        "video_id": "48b679da-5cba-48ac-98f1-885e739e31c1",
        "camera_id": "8634f0a2-d118-4840-8970-366213cd2f5b",
        "name": "Port de Ceinture",
        "zones": ["Zone_bbox"],
        "lines": [],
    },
]

def psql(sql: str) -> str:
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        raise SystemExit(1)
    return r.stdout.strip()

def psql_exec(sql: str) -> None:
    subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", sql],
        check=True,
    )

site_id = psql(f"SELECT id FROM sites WHERE org_id = '{ORG}'::uuid ORDER BY created_at LIMIT 1;")
if not site_id:
    print("[FAIL] No site for org", ORG)
    sys.exit(1)

active_video = None
for spec in SPECS:
    vid = spec["video_id"]
    cam_id = spec["camera_id"]
    fname = f"{vid}_stream.mp4"
    fpath = VIDEOS_DIR / fname
    if not fpath.is_file():
        print(f"[SKIP] missing file {fname}")
        continue
    size = fpath.stat().st_size
    go2rtc = f"demo-{ORG[:8]}-{vid[:8]}"
    rel = f"demo/{ORG}/{fname}"
    local = str(fpath).replace("'", "''")
    name = spec["name"].replace("'", "''")

    psql_exec(f"""
    INSERT INTO org_demo_videos (id, org_id, name, status, progress, go2rtc_src, local_stream_path, size_bytes, updated_at)
    VALUES ('{vid}'::uuid, '{ORG}'::uuid, '{name}', 'ready', 100, '{go2rtc}', '{local}', {size}, NOW())
    ON CONFLICT (id) DO UPDATE SET
      name = EXCLUDED.name,
      status = 'ready',
      progress = 100,
      go2rtc_src = EXCLUDED.go2rtc_src,
      local_stream_path = EXCLUDED.local_stream_path,
      size_bytes = EXCLUDED.size_bytes,
      updated_at = NOW();
    """)

    meta = {
        "virtual": True,
        "demo": True,
        "go2rtc_src": go2rtc,
        "video_file": str(fpath),
        "demo_video_id": vid,
        "ai_ingest": "file",
        "source": "demo-upload",
    }
    meta_json = json.dumps(meta).replace("'", "''")
    cam_name = f"Démo — {spec['name']}".replace("'", "''")
    rtsp = f"/{go2rtc}"

    psql_exec(f"""
    INSERT INTO cameras (id, org_id, site_id, name, vendor, host, port, rtsp_path, metadata, is_active, status)
    VALUES (
      '{cam_id}'::uuid, '{ORG}'::uuid, '{site_id}'::uuid, '{cam_name}', 'generic', '127.0.0.1', 8554,
      '{rtsp}', '{meta_json}'::jsonb, TRUE, 'online'
    )
    ON CONFLICT (id) DO UPDATE SET
      name = EXCLUDED.name,
      rtsp_path = EXCLUDED.rtsp_path,
      metadata = EXCLUDED.metadata,
      is_active = TRUE,
      status = 'online',
      updated_at = NOW();
    """)

    for zn in spec["zones"]:
        zn_esc = zn.replace("'", "''")
        psql_exec(f"UPDATE zones SET camera_id = '{cam_id}'::uuid WHERE name = '{zn_esc}' AND org_id = '{ORG}'::uuid;")
    for ln in spec["lines"]:
        ln_esc = ln.replace("'", "''")
        psql_exec(f"UPDATE lines SET camera_id = '{cam_id}'::uuid WHERE name = '{ln_esc}' AND org_id = '{ORG}'::uuid;")

    print(f"[OK] {spec['name']} — video {vid[:8]} + camera {cam_id[:8]}")
    if spec["name"] == "Ligne Continue":
        active_video = vid

if active_video:
    psql_exec(f"""
    UPDATE org_demo_settings SET
      active_video_id = '{active_video}'::uuid,
      active_camera_id = '{SPECS[1]["camera_id"]}'::uuid,
      source_mode = 'video',
      updated_at = NOW()
    WHERE org_id = '{ORG}'::uuid;
    """)
    print(f"[OK] Active source: Ligne Continue ({active_video[:8]})")

print("[OK] DB rehydration complete")
PY

echo "==> 3/7 Playback + go2rtc"
bash "$ROOT/scripts/fix-demo-video-playback.sh" 2>&1 | tail -15

echo "==> 4/7 Seed spatial behaviors + demo rules"
bash "$ROOT/scripts/seed-demo-spatial.sh"
DEMO_RULES_ENABLED=0 bash "$ROOT/scripts/seed-demo-rules.sh"

echo "==> 5/7 Spatial reload + AI ingest"
bash "$ROOT/scripts/force-spatial-reload.sh" 2>&1 | tail -8
bash "$ROOT/scripts/restart-ai-ingest.sh" 2>&1 | tail -5

echo "==> 6/7 Vérification API"
TOKEN=$(curl -sf -X POST "$API/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl -sf "$API/api/v1/orgs/$ORG/demo/settings" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; s=json.load(sys.stdin); print('videos:', len(s.get('videos',[])), 'stream:', s.get('active_go2rtc_src',''))"
curl -sf "$API/api/v1/orgs/$ORG/cameras" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; c=json.load(sys.stdin); d=[x for x in c if 'Démo' in x.get('name','')]; print('demo cameras:', len(d)); [print(' -', x['name']) for x in d]"

echo "==> 7/7 Terminé"
echo ""
echo "  Ouvrez http://localhost:5174/demo"
echo "  Les 5 règles démo sont recréées (désactivées par défaut — réactivez dans Règles)."
echo "  Vos zones/lignes existantes sont reliées aux caméras virtuelles."
echo ""
