#!/usr/bin/env bash
set -euo pipefail
ENV=/home/gheno/citevision-v2/.env
# upsert align
if grep -q '^FRIGATE_DEMO_ACCEPT_MAX_ALIGN_SEC=' "$ENV"; then
  sed -i 's/^FRIGATE_DEMO_ACCEPT_MAX_ALIGN_SEC=.*/FRIGATE_DEMO_ACCEPT_MAX_ALIGN_SEC=20/' "$ENV"
else
  echo 'FRIGATE_DEMO_ACCEPT_MAX_ALIGN_SEC=20' >> "$ENV"
fi
grep FRIGATE_DEMO_ACCEPT "$ENV"
# fix accidental literal \n from prior bad write
if grep -q '\\n' "$ENV"; then
  python3 - <<'PY'
from pathlib import Path
p = Path("/home/gheno/citevision-v2/.env")
t = p.read_text()
if "\\n" in t and "\n" not in t.replace("\\n", ""):
    p.write_text(t.replace("\\n", "\n"))
    print("fixed literal backslash-n")
else:
    # only replace if file looks flattened
    if t.count("\\n") > 5 and t.count("\n") < 3:
        p.write_text(t.replace("\\n", "\n"))
        print("fixed flattened env")
    else:
        print("env newlines ok", t.count("\n"))
PY
fi
