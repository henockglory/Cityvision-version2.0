"""Plate XOR + list/repeat matching without re-OCR."""

from __future__ import annotations

import numpy as np

from citevision_ai.identity.plate import PlateIdentityEngine


def test_plate_process_frame_xor_when_bridge_active():
    eng = PlateIdentityEngine()
    eng.set_frigate_bridge_active(True)
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    assert eng.process_frame("cam", frame, [], "2026-01-01T00:00:00Z") == []


def test_plate_list_and_repeat_no_reocr():
    eng = PlateIdentityEngine()
    eng.set_plates([
        {"identifier": "ABC123", "metadata": {"status": "blocked"}},
        {"identifier": "XYZ999", "metadata": {"status": "allowed"}},
    ])
    assert eng._match_plate("ABC123") == "blocked"
    assert eng._match_plate("XYZ999") == "allowed"
    assert eng._match_plate("UNKNOWN1") == "unknown"
    assert eng.is_repeat_sighting("cam", "ABC123") is False
    eng.remember_sighting("cam", "ABC123")
    assert eng.is_repeat_sighting("cam", "ABC123") is True
