#!/usr/bin/env bash
set -euo pipefail
SRC=/mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/evidence/service.py
DST=/home/gheno/citevision-v2/ai-engine/src/citevision_ai/evidence/service.py
wc -c "$SRC" "$DST"
md5sum "$SRC" "$DST"
python3 - <<'PY'
from pathlib import Path
for p in [
    Path("/mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/evidence/service.py"),
    Path("/home/gheno/citevision-v2/ai-engine/src/citevision_ai/evidence/service.py"),
]:
    lines = p.read_bytes().splitlines()
    print(p, "line25", repr(lines[24]))
PY
# Force copy + strip + verify
cp -f "$SRC" "$DST"
sed -i 's/\r$//' "$DST"
python3 - <<'PY'
from pathlib import Path
p = Path("/home/gheno/citevision-v2/ai-engine/src/citevision_ai/evidence/service.py")
line = p.read_text().splitlines()[24]
print("AFTER", repr(line))
assert "FrameRingBuffer" in line, line
assert "FrameRingBuffe\n" not in line + "\n"
print("OK import line")
PY
