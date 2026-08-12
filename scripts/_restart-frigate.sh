#!/usr/bin/env bash
set -euo pipefail
echo 'restarting frigate...'
docker restart citevision-v2-frigate
for i in $(seq 1 60); do
  if curl -sf -m 3 http://127.0.0.1:5000/api/stats >/dev/null 2>&1; then
    echo "frigate healthy after ${i} attempts"
    break
  fi
  sleep 3
done
curl -sf -m 10 http://127.0.0.1:5000/api/config -o /tmp/frc.json
python3 -c 'import json;c=json.load(open("/tmp/frc.json"));print("track", c["cameras"]["cv_cdf09f43-d4c7-4c51-9ae9-9493970fdd5d"]["objects"]["track"]);print("face_rec", c.get("face_recognition"))'
# ensure person
python3 <<'PY'
import json
from pathlib import Path
c=json.load(open('/tmp/frc.json'))
track=c['cameras']['cv_cdf09f43-d4c7-4c51-9ae9-9493970fdd5d']['objects']['track']
if 'person' in track:
  print('OK person tracked')
  raise SystemExit(0)
print('NEED PATCH')
p=Path('/home/gheno/citevision-v2/infra/frigate-config/config.yml')
text=p.read_text()
cam='    cv_cdf09f43-d4c7-4c51-9ae9-9493970fdd5d:'
idx=text.find(cam)
ot=text.find('        objects:\n            track:', idx)
if '- person' not in text[ot:ot+350].split('live:')[0]:
  insert_at=text.find('\n                - ', ot)
  text=text[:insert_at]+'\n                - person'+text[insert_at:]
  p.write_text(text)
  print('patched yml')
PY
if ! python3 -c 'import json;print("person" in json.load(open("/tmp/frc.json"))["cameras"]["cv_cdf09f43-d4c7-4c51-9ae9-9493970fdd5d"]["objects"]["track"])' | grep -q True; then
  if [[ "${FRIGATE_ALLOW_RELOAD:-0}" == "1" ]]; then
    curl -sf -X POST http://127.0.0.1:5000/api/reload
  else
    echo "[diag] skip /api/reload (set FRIGATE_ALLOW_RELOAD=1 to force)"
  fi
  sleep 8
  curl -sf -m 10 http://127.0.0.1:5000/api/config -o /tmp/frc.json
  python3 -c 'import json;c=json.load(open("/tmp/frc.json"));print("track after reload", c["cameras"]["cv_cdf09f43-d4c7-4c51-9ae9-9493970fdd5d"]["objects"]["track"])'
fi
docker ps --filter name=citevision-v2-frigate --format '{{.Status}}'
curl -sf http://127.0.0.1:8001/health -o /tmp/aih.json
python3 -c 'import json;d=json.load(open("/tmp/aih.json"));print("AI",d.get("status"),"face",d.get("frigate_bridge_face_enqueued"),"snap_fail",d.get("frigate_bridge_snapshot_fail"),"mqtt",d.get("frigate_bridge_mqtt"))'
