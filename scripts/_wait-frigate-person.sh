#!/usr/bin/env bash
set -euo pipefail
echo "Frigate container:"
docker ps -a --filter name=citevision-v2-frigate --format '{{.Status}}'
docker start citevision-v2-frigate 2>/dev/null || true
echo "Waiting Frigate API..."
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:5000/api/stats >/dev/null 2>&1; then
    echo "up in ${i} attempts"
    break
  fi
  sleep 2
done
curl -sf http://127.0.0.1:5000/api/config -o /tmp/fr.json
python3 <<'PY'
import json
c=json.load(open("/tmp/fr.json"))
cam=c["cameras"]["cv_cdf09f43-d4c7-4c51-9ae9-9493970fdd5d"]
print("track:", cam.get("objects",{}).get("track"))
print("face_recognition:", c.get("face_recognition"))
PY
# ensure person still there
python3 <<'PY'
import json
from pathlib import Path
c=json.load(open("/tmp/fr.json"))
track=c["cameras"]["cv_cdf09f43-d4c7-4c51-9ae9-9493970fdd5d"].get("objects",{}).get("track") or []
if "person" in track:
  print("OK person tracked")
  raise SystemExit(0)
print("REPATCH needed")
p=Path("/home/gheno/citevision-v2/infra/frigate-config/config.yml")
text=p.read_text()
cam="    cv_cdf09f43-d4c7-4c51-9ae9-9493970fdd5d:"
idx=text.find(cam)
ot=text.find("        objects:\n            track:", idx)
chunk=text[ot:ot+350]
if "- person" not in chunk.split("live:")[0]:
  insert_at=text.find("\n                - ", ot)
  text=text[:insert_at]+"\n                - person"+text[insert_at:]
  p.write_text(text)
  print("patched config.yml")
PY
if ! python3 -c 'import json;c=json.load(open("/tmp/fr.json"));print("person" in (c["cameras"]["cv_cdf09f43-d4c7-4c51-9ae9-9493970fdd5d"].get("objects",{}).get("track") or []))' | grep -q True; then
  if [[ "${FRIGATE_ALLOW_RELOAD:-0}" == "1" ]]; then
    curl -sf -X POST http://127.0.0.1:5000/api/reload || true
  else
    echo "[diag] skip /api/reload (set FRIGATE_ALLOW_RELOAD=1 to force)"
  fi
  sleep 10
  curl -sf http://127.0.0.1:5000/api/config -o /tmp/fr.json
  python3 <<'PY'
import json
print("track after reload:", json.load(open("/tmp/fr.json"))["cameras"]["cv_cdf09f43-d4c7-4c51-9ae9-9493970fdd5d"]["objects"]["track"])
PY
fi
