#!/usr/bin/env python3
"""Pin onnxruntime-gpu to 1.19.2 in pyproject.toml"""
from pathlib import Path
import re

pyproject = Path("ai-engine/pyproject.toml")
content = pyproject.read_text(encoding="utf-8")

# Pin the version for non-Darwin (Linux/WSL)
OLD = '"onnxruntime-gpu>=1.17; platform_system != \'Darwin\'",'
NEW = '"onnxruntime-gpu==1.19.2; platform_system != \'Darwin\'",  # pinned: CUDA WSL requires 1.19.x with CUDA 11.8 compat'
if OLD in content:
    content = content.replace(OLD, NEW)
    pyproject.write_text(content, encoding="utf-8")
    print("Pinned onnxruntime-gpu to 1.19.2")
else:
    # Try without trailing comma
    OLD2 = '"onnxruntime-gpu>=1.17; platform_system != \'Darwin\'"'
    NEW2 = '"onnxruntime-gpu==1.19.2; platform_system != \'Darwin\'"  # pinned: CUDA WSL requires 1.19.x'
    if OLD2 in content:
        content = content.replace(OLD2, NEW2)
        pyproject.write_text(content, encoding="utf-8")
        print("Pinned onnxruntime-gpu to 1.19.2 (no trailing comma)")
    else:
        print("Anchor not found - current onnx lines:")
        for i, line in enumerate(content.split('\n'), 1):
            if 'onnxruntime-gpu' in line:
                print(f"  L{i}: {repr(line)}")
