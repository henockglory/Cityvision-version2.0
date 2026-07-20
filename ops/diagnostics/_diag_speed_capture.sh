#!/usr/bin/env bash
set -euo pipefail
echo "=== code markers ==="
grep -c '_begin_speed_evidence' /home/gheno/citevision-v2/ai-engine/src/citevision_ai/evidence/service.py || true
grep -c 'speed evidence dedupe' /home/gheno/citevision-v2/ai-engine/src/citevision_ai/evidence/service.py || true
echo "=== log markers ==="
grep -c 'speed evidence' /home/gheno/citevision-v2/logs/ai-engine.log || true
grep -c 'retroactive semaphore' /home/gheno/citevision-v2/logs/ai-engine.log || true
grep -c 'dedupe skip' /home/gheno/citevision-v2/logs/ai-engine.log || true
grep -c 'no correlated' /home/gheno/citevision-v2/logs/ai-engine.log || true
grep -c 'demo vehicle fallback' /home/gheno/citevision-v2/logs/ai-engine.log || true
grep -c 'clip ok' /home/gheno/citevision-v2/logs/ai-engine.log || true
echo "=== frigate events ==="
python3 <<'PY'
import json, urllib.request, time
fc = "cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
ev = json.loads(urllib.request.urlopen(
    f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=5", timeout=8
).read())
now = time.time()
for e in ev:
    print(
        f"id={e['id'][:28]} age={now-float(e['start_time']):.1f}s "
        f"label={e.get('label')} clip={e.get('has_clip')} snap={e.get('has_snapshot')} "
        f"start={e.get('start_time')}"
    )
print("now", now)
PY
echo "=== env align ==="
grep -E 'FRIGATE_DEMO|FRIGATE_CORRELATE|DEMO_EVIDENCE|EVIDENCE_BACKEND' /home/gheno/citevision-v2/.env | head -30
echo "=== rules recent ==="
grep -E 'incomplete_evidence|capture unavailable|alert suppressed|ensureEvidence' /home/gheno/citevision-v2/logs/rules-engine.log | tail -20
