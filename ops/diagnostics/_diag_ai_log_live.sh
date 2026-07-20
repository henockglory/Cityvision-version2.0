#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
echo "log bytes $(wc -c < $ROOT/logs/ai-engine.log)"
echo "=== all evidence/frigate/dedupe lines ==="
grep -E 'speed evidence|frigate_track|evidence semaphore|capture unavailable|strict_frigate|retro|ENCODE|mark_frigate|evidence_status' \
  "$ROOT/logs/ai-engine.log" | tail -80
echo "=== settings align ==="
"$ROOT/ai-engine/.venv/bin/python" - <<'PY'
from citevision_ai.config import settings
print("max_align", settings.frigate_demo_max_align_sec)
print("accept", settings.frigate_demo_accept_max_align_sec)
print("demo_mode", settings.demo_mode)
print("demo_backend", settings.demo_evidence_backend)
print("evidence_backend", settings.evidence_backend)
print("frigate_enabled", getattr(settings, "frigate_enabled", None) or getattr(settings, "frigate_url", None))
PY
echo "=== frigate fresh? ==="
curl -sf "http://127.0.0.1:5000/api/events?cameras=cv_55694d53-8f58-4981-91b2-7c6cd528a25d&limit=2" \
  | python3 -c 'import sys,json,time; ev=json.load(sys.stdin); now=time.time();
print([(e.get("id","")[:20], round(now-float(e["start_time"]),1), e.get("has_clip")) for e in ev])'
