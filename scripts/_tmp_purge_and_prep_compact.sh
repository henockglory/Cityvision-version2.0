#!/usr/bin/env bash
# Purge preuves + Frigate recordings (≈180Go) puis fstrim — compact VHDX = étape admin Windows.
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

echo "=== AVANT ==="
df -h / /mnt/c | sed -n '1,3p'
docker exec citevision-v2-minio du -sh /data /data/citevision-evidence 2>/dev/null || true
docker run --rm -v infra_frigate_recordings:/v:ro alpine du -sh /v 2>/dev/null || true
docker run --rm -v infra_frigate_clips:/v:ro alpine du -sh /v 2>/dev/null || true
sudo du -sh /var/lib/docker/volumes/infra_frigate_recordings /var/lib/docker/volumes/infra_minio_data /var/lib/docker/volumes/infra_frigate_clips 2>/dev/null || true

echo "=== wait postgres+minio ==="
for i in $(seq 1 30); do
  docker exec citevision-v2-postgres pg_isready -U citevision >/dev/null 2>&1 \
    && docker exec citevision-v2-minio ls /data >/dev/null 2>&1 && break
  sleep 2
done

export ADMIN_PASSWORD='Hologram2026!'
# Don't re-enable all demo rules during disk purge
export REENABLE_DEMO_RULES=0

# Fast purge (DB + MinIO evidence + Frigate recordings + clips locaux)
sed -i 's/\r$//' /mnt/c/Users/gheno/citevision/scripts/purge_all_evidence_fast.py
cp -f /mnt/c/Users/gheno/citevision/scripts/purge_all_evidence_fast.py "$ROOT/scripts/"
# Patch: skip rules re-enable via env if we run a slim version — use python with skip
python3 - <<'PY'
import os, sys
sys.path.insert(0, "/home/gheno/citevision-v2/scripts")
# run purge body without re-enable by monkeypatching
import purge_all_evidence_fast as p

def skip_rules(self=None):
    print("=== skip rules re-enable (disk purge) ===")
    return

# Replace the re-enable section by editing main flow: call functions manually
from pathlib import Path
import json, time, subprocess, urllib.request

ROOT = Path.home() / "citevision-v2"
print("=== AVANT ===")
print(p.psql("SELECT 'alerts', count(*) FROM alerts UNION ALL SELECT 'events', count(*) FROM events;"))
print(f"MinIO evidence: {p.du_docker('/data/citevision-evidence')}")

print("\n=== Stop IA ===")
for pat in ("citevision-ai", "run-ai-engine", "uvicorn citevision_ai"):
    subprocess.run(["pkill", "-f", pat], capture_output=True)
time.sleep(2)

print("\n=== TRUNCATE DB ===")
p.psql("TRUNCATE TABLE alerts RESTART IDENTITY CASCADE;", timeout=600)
p.psql("TRUNCATE TABLE events RESTART IDENTITY CASCADE;", timeout=3600)
r = p.run(
    ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c",
     "SELECT to_regclass('public.evidence_objects');"],
    check=False,
)
if (r.stdout or "").strip() == "evidence_objects":
    p.psql("TRUNCATE TABLE evidence_objects RESTART IDENTITY CASCADE;", timeout=600)
try:
    p.psql("UPDATE rule_counters SET count=0, last_event_type='', updated_at=NOW();", timeout=120)
except Exception:
    pass
p.psql("VACUUM ANALYZE alerts;", timeout=300)
p.psql("VACUUM ANALYZE events;", timeout=300)

print("\n=== Purge MinIO evidence ===")
r = p.run(
    "docker exec citevision-v2-minio sh -c 'rm -rf /data/citevision-evidence && mkdir -p /data/citevision-evidence && echo done'",
    timeout=1800, check=False,
)
print(r.stdout or r.stderr)

print("\n=== Purge Frigate recordings (≈186G) ===")
p.run(
    "docker run --rm -v infra_frigate_recordings:/v alpine sh -c 'rm -rf /v/*; echo frigate_recordings cleared'",
    timeout=1800, check=False,
)
print("\n=== Purge Frigate clips (≈4G) ===")
p.run(
    "docker run --rm -v infra_frigate_clips:/v alpine sh -c 'rm -rf /v/*; echo frigate_clips cleared'",
    timeout=600, check=False,
)

print("\n=== Purge clips locaux ===")
for base in [ROOT / "backend/data/clips", Path("/mnt/c/Users/gheno/citevision/backend/data/clips"), Path("/mnt/c/Citevision/backend/data/clips")]:
    if base.is_dir():
        import shutil
        for child in base.iterdir():
            if child.is_file():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
        print(f"  cleared {base}")

print("\n=== APRÈS purge logique ===")
print(p.psql("SELECT 'alerts', count(*) FROM alerts UNION ALL SELECT 'events', count(*) FROM events;"))
print(f"MinIO evidence: {p.du_docker('/data/citevision-evidence')}")
r2 = p.run("docker run --rm -v infra_frigate_recordings:/v:ro alpine du -sh /v", check=False)
print(f"Frigate recordings: {(r2.stdout or '?').strip()}")
r3 = p.run("docker run --rm -v infra_frigate_clips:/v:ro alpine du -sh /v", check=False)
print(f"Frigate clips: {(r3.stdout or '?').strip()}")
print("PURGE_LOGICAL_DONE")
PY

echo "=== docker prune (images inutiles, PAS volumes) ==="
docker image prune -af || true

echo "=== fstrim (marque blocs libres pour compact VHDX) ==="
sudo fstrim -av || sudo fstrim -v / || true
sync
df -h / /mnt/c | sed -n '1,3p'
sudo du -sh /var/lib/docker/volumes/infra_frigate_recordings /var/lib/docker/volumes/infra_minio_data /var/lib/docker/volumes/infra_frigate_clips 2>/dev/null || true

echo ""
echo "PURGE_DONE — prochaines etapes ADMIN Windows pour liberer ~180Go sur C:"
echo "  1) Clique droit en Admin: scripts\\compact-wsl-now-admin.bat"
echo "  OU PowerShell Admin: powershell -ExecutionPolicy Bypass -File C:\\Users\\gheno\\citevision\\scripts\\compact-wsl-vhdx.ps1"
echo "  (fait wsl --shutdown + diskpart compact du ext4.vhdx)"
