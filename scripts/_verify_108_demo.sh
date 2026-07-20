#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2

echo "=== any 108 left? ==="
grep -RIn '192.168.1.108' infra/frigate-config/ || echo "none"

echo "=== camera keys in config.yml ==="
python3 - <<'PY'
from pathlib import Path
import yaml
p = Path("infra/frigate-config/config.yml")
data = yaml.safe_load(p.read_text())
cams = data.get("cameras") or {}
print("cameras:", len(cams), sorted(cams.keys()))
for name, cfg in cams.items():
    paths = []
    for role in ("ffmpeg",):
        ff = (cfg or {}).get("ffmpeg") or {}
        for inp in ff.get("inputs") or []:
            paths.append(inp.get("path",""))
    print(f"  {name}: {[x for x in paths if x]}")
go = (data.get("go2rtc") or {}).get("streams") or {}
print("go2rtc streams:", len(go))
for k,v in list(go.items())[:12]:
    s = str(v)
    if "192.168.1.108" in s:
        print("  HAS 108:", k, s[:120])
PY

echo "=== backend skip log (text) ==="
grep -a 'frigate skip excluded\|frigate config rebuilt' logs/backend.log | tail -8

echo "=== DEMO_MODE resolve without environ ==="
unset DEMO_MODE CITEVISION_DEMO_MODE
cd ~/citevision-v2/ai-engine
python3 - <<'PY'
import os, sys
sys.path.insert(0, "src")
# Ensure not inherited
for k in ("DEMO_MODE", "CITEVISION_DEMO_MODE"):
    os.environ.pop(k, None)
from citevision_ai.config import resolve_demo_mode, Settings
demo, src = resolve_demo_mode()
print("resolve_demo_mode:", demo, src)
s = Settings()
print("Settings.demo_mode:", s.demo_mode, "source:", s.demo_mode_source, "relaxed:", s.demo_relaxed_evidence())
PY
