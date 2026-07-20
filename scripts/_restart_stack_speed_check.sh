#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

# Ensure test file synced
cp -f /mnt/c/Users/gheno/citevision/ai-engine/tests/test_speed_evidence_dedupe.py \
  "$ROOT/ai-engine/tests/test_speed_evidence_dedupe.py" 2>/dev/null || true
sed -i 's/\r$//' "$ROOT/ai-engine/src/citevision_ai/evidence/service.py" \
  "$ROOT/ai-engine/tests/test_speed_evidence_dedupe.py" 2>/dev/null || true

bash scripts/restart-ai-engine.sh
bash scripts/_start-rules-engine.sh

echo "=== go2rtc streams ==="
curl -sf --max-time 5 http://127.0.0.1:1984/api/streams -o /tmp/go2rtc_streams.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/go2rtc_streams.json"))
print("n_streams", len(d))
for k in sorted(d)[:20]:
    print(" ", k)
demos=[k for k in d if "demo" in k.lower()]
print("demo_streams", demos)
PY

echo "=== frigate fps ==="
curl -sf --max-time 8 http://127.0.0.1:5000/api/stats -o /tmp/frigate_stats.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/frigate_stats.json"))
cams=d.get("cameras") or {}
print("n_cameras", len(cams))
for k,v in cams.items():
    print(f"  {k}: fps={v.get('camera_fps')} det={v.get('detection_fps')}")
PY

echo "=== backend/ai/rules health ==="
curl -sf http://127.0.0.1:8081/health && echo
curl -sf http://127.0.0.1:8001/health | python3 -m json.tool | head -40
curl -sf http://127.0.0.1:8010/health | python3 -m json.tool
