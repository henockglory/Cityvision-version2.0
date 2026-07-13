"""Unit tests for Frigate correlation accept gate (align <= 5s)."""
from __future__ import annotations

from citevision_ai.evidence.frigate_track_evidence import FrigateTrackEvidence


def test_accept_correlation_rejects_large_align():
    svc = FrigateTrackEvidence()
    evt = {
        "bbox_ts": 1009.0,
        "bbox": {"x1": 0.05, "y1": 0.05, "x2": 0.15, "y2": 0.15},
        "class_name": "car",
    }
    matched = {"start_time": 1000.0, "data": {"box": [100, 100, 200, 200]}}
    assert svc._accept_correlation(evt, matched, 9.0, "") is False


def test_accept_correlation_accepts_tight_align():
    svc = FrigateTrackEvidence()
    evt = {
        "bbox_ts": 1000.4,
        "bbox": {"x1": 0.05, "y1": 0.05, "x2": 0.15, "y2": 0.15},
        "class_name": "car",
    }
    matched = {"start_time": 1000.0, "data": {"box": [100, 100, 200, 200]}}
    assert svc._accept_correlation(evt, matched, 0.4, "") is True
