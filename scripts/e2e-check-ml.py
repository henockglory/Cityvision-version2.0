#!/usr/bin/env python3
import sys

for mod in ("insightface", "paddleocr"):
    try:
        __import__(mod)
        print(f"{mod}: OK")
    except Exception as exc:
        print(f"{mod}: FAIL {exc}")
