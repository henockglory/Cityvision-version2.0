#!/usr/bin/env python3
"""Normalise shell scripts for WSL/bash: strip UTF-8 BOM and CRLF."""
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "scripts"
fixed = 0
for p in root.rglob("*.sh"):
    data = p.read_bytes()
    orig = data
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    if b"\r" in data:
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if data != orig:
        p.write_bytes(data)
        print("fixed", p.relative_to(root.parent))
        fixed += 1
print(f"done ({fixed} file(s) updated)")
