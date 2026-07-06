#!/usr/bin/env python3
"""Purge all MinIO evidence and local clips."""
import subprocess, os, glob

def run(cmd, timeout=300):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip(), r.stderr.strip(), r.returncode

def du(path):
    out, _, _ = run(f"du -sh {path} 2>/dev/null")
    return out.split()[0] if out else "?"

clips_dir = os.path.expanduser("~/citevision-v2/backend/data/clips")

print("=== AVANT ===")
print(f"  Clips locaux: {du(clips_dir)}")
out, _, _ = run("docker exec citevision-v2-minio du -sh /data/citevision-evidence 2>/dev/null")
print(f"  MinIO evidence: {out.split()[0] if out else '?'}")

# 1. Local clips
print("\n=== Purge clips locaux ===")
if os.path.isdir(clips_dir):
    files = [f for f in glob.glob(os.path.join(clips_dir, "*")) if os.path.isfile(f)]
    for f in files:
        try:
            os.remove(f)
        except OSError as e:
            print(f"  WARN: {f}: {e}")
    print(f"  Supprimé {len(files)} fichiers")
else:
    print("  Dossier absent")

# 2. MinIO evidence (entire orgs tree)
print("\n=== Purge MinIO citevision-evidence ===")
out, err, rc = run(
    "docker exec citevision-v2-minio sh -c "
    "'rm -rf /data/citevision-evidence/orgs && mkdir -p /data/citevision-evidence/orgs'",
    timeout=600,
)
if rc != 0:
    print(f"  ERREUR: {err or out}")
else:
    print("  Bucket citevision-evidence/orgs vidé")

print("\n=== APRÈS ===")
print(f"  Clips locaux: {du(clips_dir)}")
out, _, _ = run("docker exec citevision-v2-minio du -sh /data/citevision-evidence 2>/dev/null")
print(f"  MinIO evidence: {out.split()[0] if out else '?'}")
out, _, _ = run("df -h /mnt/c 2>/dev/null | tail -1")
print(f"  Disque C: {out}")
