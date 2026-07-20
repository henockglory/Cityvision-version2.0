#!/usr/bin/env bash
set -uo pipefail
cd ~/citevision-v2

echo "=== git tags ==="
git tag -l | head -80
echo "--- tags matching pass/valid/rule ---"
git tag -l '*pass*' '*valid*' '*speed*' '*phone*' '*seat*' '*count*' '*red*' '*feu*' 2>/dev/null | head -40

echo
echo "=== validation-evidence artefacts ==="
if [[ -d validation-evidence ]]; then
  find validation-evidence -maxdepth 3 -type d 2>/dev/null | head -80
  echo "--- counts per alias ---"
  for d in validation-evidence/*/; do
    [[ -d "$d" ]] || continue
    n=$(find "$d" -type f 2>/dev/null | wc -l)
    oldest=$(find "$d" -type f -printf '%T+ %p\n' 2>/dev/null | sort | head -1)
    newest=$(find "$d" -type f -printf '%T+ %p\n' 2>/dev/null | sort | tail -1)
    echo "$d files=$n oldest=$oldest newest=$newest"
  done
else
  echo "no validation-evidence dir"
  find . -type d -name 'validation-evidence' 2>/dev/null | head
fi

echo
echo "=== scripts _fix_ / _diag_ counts ==="
echo "fix: $(ls scripts/_fix_* 2>/dev/null | wc -l)"
echo "diag: $(ls scripts/_diag_* 2>/dev/null | wc -l)"
echo "executable fix: $(find scripts -name '_fix_*' -perm -111 2>/dev/null | wc -l)"
echo "executable diag: $(find scripts -name '_diag_*' -perm -111 2>/dev/null | wc -l)"

echo
echo "=== validate_rule.sh vs peers ==="
ls scripts/validate_rule.sh scripts/validate_rule_dod.py scripts/_validate_rule_frigate_1hit.py 2>&1
ls scripts/validate*.sh scripts/validate*.py 2>/dev/null | wc -l

echo
echo "=== demo video MP4 durations ==="
find . -iname '*feu*' -o -iname '*red*' -o -iname '*traffic*' 2>/dev/null | head -5
# org demo videos
find data demo_videos storage media org_demo -iname '*.mp4' 2>/dev/null | head -40
ls -lh data/demo_videos 2>/dev/null | head
ls -lh storage/demo 2>/dev/null | head

# from DB path if any
python3 - <<'PY'
import os, subprocess, json
from pathlib import Path
# search common places
roots=[Path("data"), Path("storage"), Path("demo"), Path("media"), Path("infra")]
found=[]
for r in roots:
  if not r.exists():
    continue
  for p in r.rglob("*.mp4"):
    found.append(p)
print("mp4_count", len(found))
for p in found[:30]:
  try:
    out=subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(p)], text=True).strip()
  except Exception as e:
    out=f"err:{e}"
  print(f"{out}\t{p}")
PY

echo
echo "=== go2rtc streams ==="
curl -sf http://127.0.0.1:1984/api/streams 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print("streams", list(d.keys()) if isinstance(d,dict) else type(d));
' 2>/dev/null || curl -sf http://127.0.0.1:8554/api/streams 2>/dev/null | head -c 500 || echo "go2rtc api fail"

echo
echo "=== frigate rebuild 502 in logs last 7d ==="
# backend log
grep -a -E 'frigate.*(rebuild|502|reload)|HTTP.*502' logs/backend.log 2>/dev/null | tail -5
# count
echo "rebuild_ok: $(grep -a -c 'frigate config rebuilt' logs/backend.log 2>/dev/null || echo 0)"
echo "reload_fail: $(grep -a -c 'frigate reload failed' logs/backend.log 2>/dev/null || echo 0)"
echo "502 mentions: $(grep -a -c '502' logs/backend.log 2>/dev/null || echo 0)"
# last 7 days approximate by date string
python3 - <<'PY'
from pathlib import Path
from datetime import datetime, timedelta, timezone
import re
log=Path("logs/backend.log")
if not log.exists():
  print("no backend log"); raise SystemExit
cutoff=datetime.now().astimezone()-timedelta(days=7)
rebuild=0; reload_fail=0; skip108=0; http502=0
# binary-safe
text=log.read_bytes().decode("utf-8","replace")
for line in text.splitlines():
  # try parse json time
  m=re.search(r'"time":"([^"]+)"', line)
  if m:
    try:
      ts=datetime.fromisoformat(m.group(1))
    except Exception:
      continue
    if ts < cutoff:
      continue
  else:
    continue
  if "frigate config rebuilt" in line:
    rebuild+=1
  if "frigate reload failed" in line:
    reload_fail+=1
  if "frigate skip excluded" in line:
    skip108+=1
  if "502" in line:
    http502+=1
print(f"last7d rebuild={rebuild} reload_fail={reload_fail} skip108={skip108} lines_with_502={http502}")
PY
