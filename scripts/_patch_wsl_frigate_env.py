#!/usr/bin/env python3
"""Patch WSL .env with Frigate evidence runtime flags."""
from pathlib import Path

ENV = Path("/home/gheno/citevision-v2/.env")
PAIRS = {
    "FRIGATE_ENABLED": "true",
    "FRIGATE_CONFIG_SYNC": "true",
    "FRIGATE_LIVE": "true",
    "FRIGATE_EVIDENCE": "true",
    "FRIGATE_EVENTS": "false",
    "FRIGATE_URL": "http://127.0.0.1:5000",
    "EVIDENCE_BACKEND": "frigate",
    "OCR_URL": "http://127.0.0.1:8181/ocr",
    "OCR_TIMEOUT": "8",
    "PLATE_MAX_FRAMES": "6",
    "PLATE_STOP_CONF": "0.88",
}

lines: list[str] = []
if ENV.exists():
    lines = ENV.read_text(encoding="utf-8").splitlines()
out: list[str] = []
seen: set[str] = set()
for line in lines:
    if "=" in line and not line.strip().startswith("#"):
        key = line.split("=", 1)[0].strip()
        if key in PAIRS:
            out.append(f"{key}={PAIRS[key]}")
            seen.add(key)
            continue
    out.append(line)
for key, val in PAIRS.items():
    if key not in seen:
        out.append(f"{key}={val}")
ENV.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"[OK] patched {ENV}")
