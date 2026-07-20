#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
CAM=8ed20433-57d5-4999-a6ab-0bea028b23a3
FC=cv_$CAM

echo "=== frigate cam config snippet ==="
python3 <<PY
import yaml, pathlib, json, urllib.request
p = pathlib.Path("/home/gheno/citevision-v2/infra/frigate-config/config.yml")
# also check generated
for cand in [
  pathlib.Path.home() / "citevision-v2/infra/frigate-config/config.yml",
  pathlib.Path("/home/gheno/citevision-v2/infra/frigate-config/config.yml"),
]:
  if cand.exists():
    cfg = yaml.safe_load(cand.read_text()) or {}
    cams = cfg.get("cameras") or {}
    fc = "$FC"
    c = cams.get(fc) or {}
    rec = (c.get("record") or {})
    snap = (c.get("snapshots") or {})
    print(f"file={cand}")
    print(f"  present={fc in cams} record.enabled={rec.get('enabled')} snapshots.enabled={snap.get('enabled')}")
    ffmpeg = (c.get("ffmpeg") or {}).get("inputs") or []
    print(f"  inputs={ffmpeg[:1]}")
    break

# live stats
try:
  st = json.loads(urllib.request.urlopen("http://127.0.0.1:5000/api/stats", timeout=8).read())
  det = (st.get("cameras") or {}).get("$FC") or {}
  print(f"stats fps={det.get('camera_fps')} detection_fps={det.get('detection_fps')} pid={det.get('pid')}")
except Exception as e:
  print("stats_err", e)

# go2rtc
try:
  streams = json.loads(urllib.request.urlopen("http://127.0.0.1:1984/api/streams", timeout=8).read())
  keys = [k for k in streams.keys() if "$CAM"[:8] in k or "8ed20433" in k or "feu" in k.lower()]
  print("go2rtc keys sample", list(streams.keys())[:8], "match", keys[:5])
except Exception as e:
  print("go2rtc_err", e)
PY

echo "=== recent events age ==="
python3 <<'PY'
import json,urllib.request,time
fc="cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"
try:
  ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=3",timeout=8).read())
  now=time.time()
  for e in ev:
    print(f"  {e['id'][:28]} age={now-float(e['start_time']):.0f}s clip={e.get('has_clip')} snap={e.get('has_snapshot')}")
    eid=e['id']
    for path in (f"clip.mp4", "snapshot.jpg", "thumbnail.jpg"):
      try:
        with urllib.request.urlopen(f"http://127.0.0.1:5000/api/events/{eid}/{path}",timeout=10) as r:
          print(f"    {path} 200 size={len(r.read(2048))}")
      except Exception as ex:
        print(f"    {path} ERR {ex}")
except Exception as e:
  print("list_err", e)
PY
