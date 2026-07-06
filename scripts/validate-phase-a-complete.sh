#!/usr/bin/env bash
# Phase A closure orchestrator [N.116–N.122] — read-only checks + optional live validation.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOG_DIR="${ROOT}/logs"
mkdir -p "$LOG_DIR"

echo "=== [1.8] Roadmap 138 status ==="
python3 scripts/generate-roadmap-138-status.py

echo "=== [N.120] Stack health ==="
if [[ -x scripts/verify-ai-ingest.sh ]]; then
  scripts/verify-ai-ingest.sh || echo "WARN: verify-ai-ingest non vert"
else
  echo "SKIP: verify-ai-ingest.sh absent"
fi

echo "=== [N.116] Demo five rules (VALIDATE_ONLY si défini) ==="
if [[ -f scripts/validate_demo_five_rules.py ]]; then
  export VALIDATE_ONLY="${VALIDATE_ONLY:-1}"
  python3 scripts/validate_demo_five_rules.py || echo "WARN: validate_demo non 5/5"
else
  echo "SKIP: validate_demo_five_rules.py absent"
fi

echo "=== [N.121] Unit tests IA géométrie ==="
if [[ -d ai-engine ]]; then
  (cd ai-engine && python3 -m pytest tests/test_zone_geometry.py -q) || echo "WARN: pytest zone_geometry"
fi

echo "=== [1.9] Porte de sortie — rapport ==="
python3 - <<'PY'
import json
from pathlib import Path
p = Path("docs/ROADMAP-138-STATUS.json")
d = json.loads(p.read_text(encoding="utf-8"))
c = d.get("counts", {})
done = c.get("done", 0)
partial = c.get("partial", 0)
pending = c.get("pending", 0)
deferred = c.get("deferred", 0)
print(f"138 points: done={done} partial={partial} pending={pending} deferred={deferred}")
gate = pending + deferred
if gate > 0:
    print(f"Phase A 1.9: NON — {gate} points pending/deferred")
else:
    print("Phase A 1.9: checklist technique OK (revalidation humaine requise)")
PY

echo "Done. Voir docs/ROADMAP-138-STATUS.json"
