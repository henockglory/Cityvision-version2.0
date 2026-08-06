#!/usr/bin/env python3
import json
import subprocess

aid = "748002fa-4fa8-46bb-ac43-adabb1972a14"
r = subprocess.run(
    [
        "docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision",
        "-t", "-A", "-c", f"SELECT evidence_snapshot::text FROM alerts WHERE id='{aid}'::uuid;",
    ],
    capture_output=True, text=True, check=False,
)
snap = json.loads((r.stdout or "").strip())
pkg = snap.get("package") if isinstance(snap.get("package"), dict) else snap
images = pkg.get("images") or []
print("images count", len(images))
for i, img in enumerate(images):
    if isinstance(img, dict):
        print(i, "keys", sorted(img.keys()), "role", img.get("role"))
clip = pkg.get("clip")
print("clip type", type(clip).__name__, "keys", sorted(clip.keys()) if isinstance(clip, dict) else None)
