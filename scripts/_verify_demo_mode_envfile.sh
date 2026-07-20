#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2
# Use AI venv if present
if [[ -x ai-engine/.venv/bin/python ]]; then
  PY=ai-engine/.venv/bin/python
elif [[ -x .venv/bin/python ]]; then
  PY=.venv/bin/python
else
  PY=python3
fi
echo "PY=$PY"
unset DEMO_MODE CITEVISION_DEMO_MODE
"$PY" - <<'PY'
import os, sys
sys.path.insert(0, "ai-engine/src")
for k in ("DEMO_MODE", "CITEVISION_DEMO_MODE"):
    os.environ.pop(k, None)
from citevision_ai.config import resolve_demo_mode, Settings
demo, src = resolve_demo_mode()
print("resolve_demo_mode:", demo, src)
s = Settings()
print("Settings.demo_mode:", s.demo_mode)
print("source:", s.demo_mode_source)
print("relaxed:", s.demo_relaxed_evidence())
assert demo is True, "DEMO_MODE=1 in .env must resolve True without environ"
assert "env_file" in src, f"expected env_file source, got {src}"
print("OK env_file fallback")
PY
