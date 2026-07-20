#!/usr/bin/env bash
# Phase A Tâche 9 — tags PASS + archive scripts + evidence rotation
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

echo "=== recent PASS artefacts ==="
python3 - <<'PY'
from pathlib import Path
import json
root=Path("validation-evidence")
latest={}
for alias_dir in sorted(root.iterdir() if root.exists() else []):
    if not alias_dir.is_dir(): continue
    alias=alias_dir.name
    best=None
    for d in sorted(alias_dir.iterdir(), reverse=True):
        rj=d/"report.json"
        if not rj.exists(): continue
        try:
            data=json.loads(rj.read_text())
        except Exception:
            continue
        if str(data.get("result","")).upper()=="PASS":
            best=d
            break
    latest[alias]=str(best) if best else None
for k,v in latest.items():
    print(f"{k}: {v}")
Path("/tmp/phaseA_pass_map.json").write_text(json.dumps(latest, indent=2))
PY

echo "=== create annotated tags (local only) ==="
# Use lightweight tags pointing at current HEAD with artefact path in message
HEAD=$(git rev-parse HEAD)
echo "HEAD=$HEAD"
MAP=$(cat /tmp/phaseA_pass_map.json)
python3 - <<'PY'
import json, subprocess, os
from pathlib import Path
latest=json.loads(Path("/tmp/phaseA_pass_map.json").read_text())
# aliases for phase A
for alias, path in latest.items():
    if not path:
        print(f"SKIP tag {alias}: no PASS artefact")
        continue
    tag=f"phaseA/{alias}/PASS"
    # delete local tag if exists to refresh message
    subprocess.run(["git","tag","-d",tag], capture_output=True)
    msg=f"Phase A PASS artefact: {path}"
    r=subprocess.run(["git","tag","-a",tag,"-m",msg], capture_output=True, text=True)
    if r.returncode==0:
        print(f"TAGGED {tag} -> {msg}")
    else:
        print(f"FAIL {tag}: {r.stderr.strip()}")
print("--- tags ---")
subprocess.run(["git","tag","-l","phaseA/*/PASS"])
PY

echo "=== archive redundant session helpers (not runtime) ==="
ARCH="$ROOT/scripts/_archive_phaseA_2026-07-19"
mkdir -p "$ARCH"
# Only move ephemeral _taskN helpers created this session if present
moved=0
for f in scripts/_task5_*.sh scripts/_task6_*.sh scripts/_task8_*.sh; do
  for p in $f; do
    [ -e "$p" ] || continue
    mv "$p" "$ARCH/" && echo "archived $p" && moved=$((moved+1)) || true
  done
done
# Do NOT auto-archive _diag_/_fix_ (frozen read-only policy) — list candidates only
echo "diag/fix candidates (NOT moved — P.135):"
ls scripts/_diag_*.sh scripts/_fix_*.sh 2>/dev/null | wc -l

echo "=== validation-evidence rotation (keep latest PASS per alias + last 3 any) ==="
python3 - <<'PY'
from pathlib import Path
import json, shutil
root=Path("validation-evidence")
removed=0
kept=0
for alias_dir in root.iterdir():
    if not alias_dir.is_dir(): continue
    dirs=sorted([d for d in alias_dir.iterdir() if d.is_dir()], key=lambda p: p.name, reverse=True)
    keep=set()
    # latest PASS
    for d in dirs:
        rj=d/"report.json"
        if not rj.exists(): continue
        try:
            if str(json.loads(rj.read_text()).get("result","")).upper()=="PASS":
                keep.add(d); break
        except Exception:
            pass
    # last 3 chronologically
    for d in dirs[:3]:
        keep.add(d)
    for d in dirs:
        if d in keep:
            kept+=1
            continue
        # remove only empty-ish / old PARTIAL without ui? still remove to free space
        shutil.rmtree(d)
        removed+=1
        print("removed", d)
print(f"rotation kept={kept} removed={removed}")
PY

echo "T9_OK"
