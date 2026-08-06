#!/usr/bin/env python3
import json
import subprocess
import sys

aid = sys.argv[1] if len(sys.argv) > 1 else "748002fa-4fa8-46bb-ac43-adabb1972a14"
r = subprocess.run(
    [
        "docker", "exec", "citevision-v2-postgres",
        "psql", "-U", "citevision", "-d", "citevision", "-t", "-A",
        "-c", f"SELECT evidence_snapshot::text FROM alerts WHERE id='{aid}'::uuid;",
    ],
    capture_output=True,
    text=True,
    check=False,
)
raw = (r.stdout or "").strip()
if not raw:
    print("no snapshot", r.stderr)
    raise SystemExit(1)
snap = json.loads(raw)
pkg = snap.get("package") or snap
print("keys:", sorted(pkg.keys()) if isinstance(pkg, dict) else type(pkg))
meta = pkg.get("metadata") or {}
print("status:", meta.get("evidence_status"), "capture:", meta.get("capture_source"))
images = pkg.get("images") or []
print("images:", len(images), [i.get("role") for i in images if isinstance(i, dict)])
assets = pkg.get("assets") or []
print("assets:", len(assets), [a.get("role") for a in assets if isinstance(a, dict)])
for role in ("scene", "subject", "plate", "clip"):
    if role in pkg:
        print(f"pkg.{role}:", bool(pkg.get(role)))
