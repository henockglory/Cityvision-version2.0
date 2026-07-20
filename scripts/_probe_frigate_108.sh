#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
python3 - <<'PY'
import yaml
p="/home/gheno/citevision-v2/infra/frigate-config/config.yml"
d=yaml.safe_load(open(p))
cams=d.get("cameras") or {}
print("cameras", len(cams))
for k,v in cams.items():
    inp=(v.get("ffmpeg") or {}).get("inputs") or []
    path=inp[0].get("path") if inp else "?"
    print(k[:48], path)
PY
echo '--- go2rtc ---'
curl -sf http://127.0.0.1:1984/api/streams 2>/dev/null | python3 -c 'import json,sys;d=json.load(sys.stdin);print([k for k in d if "108" in k or "d2eb" in k])'
echo '--- db cam 108 ---'
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT id, name, host(host), is_active, left(metadata::text,80) FROM cameras WHERE host(host)='192.168.1.108' OR id::text LIKE 'd2eb7076%';"
