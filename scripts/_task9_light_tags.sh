#!/usr/bin/env bash
set -euo pipefail
cd /home/gheno/citevision-v2
python3 <<'PY'
import json, subprocess
from pathlib import Path
latest = json.loads(Path("/tmp/phaseA_pass_map.json").read_text())
lines = ["# Phase A PASS tags\n"]
for a, p in latest.items():
    if p:
        lines.append(f"- `phaseA/{a}/PASS` → `{p}`\n")
Path("validation-evidence/PHASEA_PASS_TAGS.md").write_text("".join(lines))
for alias, path in latest.items():
    if not path:
        continue
    tag = f"phaseA/{alias}/PASS"
    subprocess.run(["git", "tag", "-d", tag], capture_output=True)
    r = subprocess.run(["git", "tag", tag], capture_output=True, text=True)
    status = "OK" if r.returncode == 0 else "FAIL"
    print(status, tag, path, (r.stderr or "").strip())
print("---")
subprocess.run(["git", "tag", "-l", "phaseA/*/PASS"])
PY
