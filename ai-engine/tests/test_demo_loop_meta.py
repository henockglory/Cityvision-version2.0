"""Tâche 5 — demo loop position helper."""
from __future__ import annotations

from citevision_ai.evidence.service import EvidenceCaptureService


def test_demo_loop_meta_modulo():
    svc = EvidenceCaptureService()
    cam = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    svc._demo_loop_epoch[cam] = 1_000_000.0
    # 400s after epoch with 352.52 loop → position ≈ 47.48
    meta = svc._demo_loop_meta(cam, 1_000_000.0 + 400.0)
    assert meta["demo_loop_duration_sec"] == 352.52
    assert abs(meta["demo_loop_position_sec"] - (400.0 % 352.52)) < 0.01
