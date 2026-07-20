#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2
echo "=== AI env demo/frigate ==="
pid=$(cat logs/ai-engine.pid 2>/dev/null || true)
if [ -n "${pid:-}" ] && [ -d "/proc/$pid" ]; then
  tr '\0' '\n' < /proc/$pid/environ | grep -E '^(DEMO_|EVIDENCE_|FRIGATE_)' || true
else
  echo "no ai pid"
fi
echo "=== recent AI frigate/evidence lines ==="
python3 <<'PY'
from pathlib import Path
lines=Path('logs/ai-engine.log').read_text(errors='replace').splitlines()[-3000:]
keys=('frigate','evidence_status','strict','capture failed','incomplete','ring_buffer','mark_frigate','timeout')
for ln in lines:
    low=ln.lower()
    if any(k in low for k in keys):
        print(ln[:280])
PY
echo "=== rules suppressed today ==="
grep -E 'alert suppressed|ensureEvidence|EOF|502' logs/rules-engine.log | tail -30
