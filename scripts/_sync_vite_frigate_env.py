#!/usr/bin/env python3
"""Sync VITE_FRIGATE_* from root .env into frontend/.env for Vite."""
from pathlib import Path

ROOT = Path.home() / "citevision-v2"
root_env = ROOT / ".env"
front_env = ROOT / "frontend" / ".env"
keys = (
    "VITE_FRIGATE_ENABLED",
    "VITE_FRIGATE_LIVE",
    "VITE_FRIGATE_ORIGIN",
    "VITE_FRIGATE_GO2RTC_ORIGIN",
)
vals = {}
if root_env.is_file():
    for line in root_env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k in keys:
            vals[k] = v
lines = ["# Auto-synced from repo .env — do not commit secrets"]
for k in keys:
    if k in vals:
        lines.append(f"{k}={vals[k]}")
front_env.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("WROTE", front_env)
for ln in lines[1:]:
    print(ln)
