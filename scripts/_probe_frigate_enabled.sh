#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
# Probe AI evidence path via a synthetic capture... better: introspect running process
"$ROOT/ai-engine/.venv/bin/python" - <<'PY'
from citevision_ai.config import settings
from citevision_ai.evidence.frigate_track_evidence import FrigateTrackEvidence
from citevision_ai.evidence.service import EvidenceCaptureService

# Simulate backend mode like service
svc = EvidenceCaptureService.__new__(EvidenceCaptureService)
# bind real helpers by calling methods that only need settings
print("demo_mode", settings.demo_mode)
print("demo_evidence_backend", settings.demo_evidence_backend)
print("evidence_backend", settings.evidence_backend)

# read mode method source behavior
import inspect
from citevision_ai.evidence import service as mod
src = inspect.getsource(EvidenceCaptureService._evidence_backend_mode)
print(src)

ft = FrigateTrackEvidence()
print("frigate_track.enabled", ft.enabled())
print("frigate url", settings.frigate_url if hasattr(settings,'frigate_url') else getattr(settings,'frigate_base_url',None))
PY

echo "=== tail raw log ==="
tail -20 "$ROOT/logs/ai-engine.log"

echo "=== validation poll ==="
tail -15 /proc/$(pgrep -f '_validate_rule_frigate_1hit' | head -1)/fd/1 2>/dev/null || true
# Read from the terminal file is on windows; just grep log for POST evidence
grep -E 'evidence/capture|POST /cameras' "$ROOT/logs/ai-engine.log" | tail -20
