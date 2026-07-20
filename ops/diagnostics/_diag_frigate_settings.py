#!/usr/bin/env python3
"""Print AI evidence/frigate settings as loaded from .env."""
from pathlib import Path

from citevision_ai.config import settings, _env_files

print("env_files", _env_files())
for p in _env_files():
    fp = Path(p)
    if fp.exists():
        for line in fp.read_text(encoding="utf-8").splitlines():
            if "FRIGATE" in line or "EVIDENCE" in line or "OCR" in line:
                print(f"  {fp.name}: {line}")

print("frigate_enabled", settings.frigate_enabled)
print("frigate_evidence", settings.frigate_evidence)
print("evidence_backend", settings.evidence_backend)
print("frigate_url", settings.frigate_url)
print("ocr_url", settings.ocr_url)

from citevision_ai.evidence.frigate_track_evidence import FrigateTrackEvidence

eng = FrigateTrackEvidence()
print("track_enabled", eng.enabled())
