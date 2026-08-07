"""Face XOR: full-frame disabled when Frigate bridge owns identity."""

from __future__ import annotations

import numpy as np

from citevision_ai.identity.face import FaceIdentityEngine


def test_face_process_frame_xor_when_bridge_active():
    eng = FaceIdentityEngine()
    eng.set_frigate_bridge_active(True)
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    assert eng.process_frame("cam", frame, "2026-01-01T00:00:00Z") == []


def test_face_match_jpeg_empty_when_not_loaded():
    eng = FaceIdentityEngine()
    # Recognizer stub typically unloaded in unit tests
    assert eng.match_jpeg(b"not-a-jpeg") == []
    assert eng.match_jpeg(b"") == []
