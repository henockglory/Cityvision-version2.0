#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
PID=$(cat "$ROOT/logs/ai-engine.pid" 2>/dev/null || echo "")
echo "pid=$PID"
ps -p "$PID" -o lstart=,etime=,cmd= 2>/dev/null || echo "not running"
echo "=== PYTHONPATH / cwd from /proc ==="
if [ -n "$PID" ] && [ -d "/proc/$PID" ]; then
  tr '\0' '\n' < /proc/$PID/environ | grep -E 'PYTHONPATH|PWD|VIRTUAL' || true
  ls -l /proc/$PID/cwd
fi
echo "=== which service.py modules on path ==="
"$ROOT/ai-engine/.venv/bin/python" - <<'PY'
import citevision_ai.evidence.service as s
print("file", s.__file__)
print("has_any", hasattr(s.EvidenceCaptureService, "_should_skip_speed_evidence"))
src=open(s.__file__, encoding="utf-8").read()
print("has___any__", "__any__" in src)
print("class", [x for x in dir(s) if "Evidence" in x])
PY
echo "=== dedupe skip count ==="
grep -c 'speed evidence dedupe skip' "$ROOT/logs/ai-engine.log" || true
echo "=== frigate_demo_max_align_sec ==="
grep -n 'frigate_demo_max_align\|FRIGATE_DEMO_MAX_ALIGN\|frigate_demo_accept' \
  "$ROOT/ai-engine/src/citevision_ai/config.py" | head -20
grep -E '^FRIGATE_.*ALIGN|^DEMO_' "$ROOT/.env" || true
