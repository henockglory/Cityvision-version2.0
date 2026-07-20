#!/usr/bin/env python3
import subprocess, os

env = os.environ.copy()
env["PATH"] = "/usr/local/go/bin:/home/gheno/go/bin:" + env.get("PATH", "")

# verify go
r = subprocess.run(["go", "version"], capture_output=True, text=True, env=env)
print("Go:", r.stdout.strip() or r.stderr.strip())

# build
r2 = subprocess.run(
    ["go", "build", "-o", "bin/citevision-api", "./cmd/api/..."],
    capture_output=True, text=True, env=env,
    cwd="/home/gheno/citevision-v2/backend"
)
print(r2.stdout.strip())
if r2.returncode != 0:
    print("ERROR:", r2.stderr[-1000:])
else:
    print("BUILD OK")
