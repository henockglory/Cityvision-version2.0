#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

echo "=== per-cam events + zones from config ==="
python3 - <<'PY'
import json, urllib.request, yaml, time
cfg = yaml.safe_load(open("/home/gheno/citevision-v2/infra/frigate-config/config.yml"))
cams = cfg.get("cameras") or {}
now = time.time()
for name, c in cams.items():
    zones = list((c.get("zones") or {}).keys())
    objs = (c.get("objects") or {})
    track = objs.get("track")
    req = None
    # frigate 0.14+ review
    rev = c.get("review") or {}
    det = c.get("detect") or {}
    url = f"http://127.0.0.1:5000/api/events?cameras={name}&limit=5"
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            evs = json.loads(r.read().decode())
    except Exception as e:
        evs = []
        print(name[:40], "ERR", e)
        continue
    ages = []
    for e in (evs if isinstance(evs, list) else []):
        st = e.get("start_time")
        if isinstance(st, (int, float)):
            ages.append(now - float(st))
    young = min(ages) if ages else None
    print(f"{name[:48]}")
    print(f"  zones={zones[:4]} track={track} detect={det.get('enabled')} review={list(rev.keys())[:4]}")
    print(f"  events={len(evs) if isinstance(evs,list) else evs} youngest={young}")
PY

echo "=== live stats det ==="
curl -sf http://127.0.0.1:5000/api/stats | python3 -c '
import json,sys
d=json.load(sys.stdin)
for k,v in (d.get("cameras") or {}).items():
    print(k[:48], "fps", v.get("camera_fps"), "det", v.get("detection_fps"), "skipped", v.get("skipped_fps"))
'

echo "=== sample event from working cam ==="
curl -sf 'http://127.0.0.1:5000/api/events?cameras=cv_55694d53-8f58-4981-91b2-7c6cd528a25d&limit=1' | python3 -m json.tool | head -60
