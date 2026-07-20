#!/usr/bin/env bash
set -uo pipefail
cd /home/gheno/citevision-v2

echo "=== EXIT DISK ==="
df -h / /mnt/c | head -5
sudo du -sh /var/lib/docker/volumes/infra_frigate_recordings \
  /var/lib/docker/volumes/infra_minio_data \
  /var/lib/docker/volumes/infra_frigate_clips 2>/dev/null
python3 - <<'PY'
from pathlib import Path
import json
root=Path("validation-evidence")
print("=== LATEST ARTEFACTS ===")
latest={}
for alias in ["speeding","red_light","phone","seatbelt","counting"]:
    d=root/alias
    if not d.is_dir():
        latest[alias]=None; continue
    dirs=sorted([x for x in d.iterdir() if x.is_dir()], reverse=True)
    best=None
    for p in dirs:
        rj=p/"report.json"
        if not rj.exists(): continue
        data=json.loads(rj.read_text())
        best={"path":str(p),"result":data.get("result"),"alert_id":data.get("alert_id")}
        break
    latest[alias]=best
    print(alias, best)
Path("/tmp/reval_latest.json").write_text(json.dumps(latest, indent=2))
# tags
import subprocess
for alias, info in latest.items():
    if not info or not info.get("path"): continue
    tag=f"phaseA/{alias}/PASS"
    subprocess.run(["git","tag","-d",tag], capture_output=True)
    # Only tag PASS results as PASS; for PARTIAL still note in map
    if str(info.get("result","")).upper()=="PASS":
        r=subprocess.run(["git","tag",tag], capture_output=True, text=True)
        print("TAG", tag, "ok" if r.returncode==0 else r.stderr)
    else:
        print("SKIP_TAG", alias, info.get("result"))
subprocess.run(["git","tag","-l","phaseA/*/PASS"])
lines=["# Phase A reval PASS map (post-purge 2026-07-19)\n"]
for a,i in latest.items():
    lines.append(f"- `{a}`: {i}\n")
Path("validation-evidence/PHASEA_PASS_TAGS.md").write_text("".join(lines))
PY

# final demo OFF
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "UPDATE rules SET is_enabled=false WHERE name LIKE 'Démo%';" >/dev/null
FRIGATE_DEMO_RETENTION_MIN=30 bash scripts/demo-retention-purge.sh || true
sudo fstrim -v / || true
echo "=== FINAL DISK ==="
df -P /mnt/c | awk 'NR==2 {printf "C_free_GB=%d\n", $4/1024/1024}'
sudo du -s -BG /var/lib/docker/volumes/infra_frigate_recordings/_data 2>/dev/null | awk '{print "frigate_rec="$1}'
echo "P2_DONE"
