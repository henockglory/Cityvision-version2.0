#!/usr/bin/env python3
"""Patch frontend/src/types/index.ts to add partial_status and partial_reason_fr to RuleCatalogTemplate"""
from pathlib import Path

types_file = Path("frontend/src/types/index.ts")
content = types_file.read_text(encoding="utf-8")

OLD = '  tutorial?: string;\n  prerequisites?: string[];\n  unsupported_message_fr?: string;\n}'
NEW = '  tutorial?: string;\n  prerequisites?: string[];\n  unsupported_message_fr?: string;\n  partial_status?: "full" | "requires_calibration" | "requires_ocr" | "requires_face_ai" | "partial_aggregate";\n  partial_reason_fr?: string;\n}'

if 'partial_status?' in content:
    print("Already patched")
elif OLD in content:
    content = content.replace(OLD, NEW)
    types_file.write_text(content, encoding="utf-8")
    print("Patched types/index.ts")
else:
    print("ERROR: could not find anchor in types/index.ts")
    print(repr(content[content.find('tutorial?'):content.find('tutorial?')+200]))
