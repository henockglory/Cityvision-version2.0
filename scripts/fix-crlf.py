#!/usr/bin/env python3
from pathlib import Path
import sys

for rel in sys.argv[1:]:
    p = Path(rel)
    data = p.read_bytes().replace(b"\r\n", b"\n")
    p.write_bytes(data)
    print("fixed", p)
